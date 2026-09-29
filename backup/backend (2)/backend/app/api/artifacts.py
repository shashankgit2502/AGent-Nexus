"""Artifacts router — read metadata + download (ARTIFACTS.md §10).

Slice 1 surface: list a run's artifacts, fetch one artifact's metadata + versions,
and stream a download. Artifacts are created **implicitly** by agent tool calls
(Slice 2), never by a direct POST (§10) — there is therefore no create endpoint here.

Two download authorization modes, both RLS-scoped (§15):

* **Authenticated** — the normal ``X-Org-Id`` request context (the management UI).
* **Signed link** — a ``?token=`` minted by :func:`app.artifacts.signing.sign_download`
  (embedded in the AG-UI attachment, Slice 2). It needs no header, so a download card
  is a plain link; the token carries ``org_id`` and the route still loads the row under
  Row-Level Security scoped to *that* org — HMAC stops forgery, RLS stops cross-tenant.

Both paths open their **own** org-scoped session (the token path has no request org
dependency) using the same ``set_config('app.current_org', …)`` GUC pattern as
``core.deps.get_db`` / the ingestion worker (R2).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.artifacts.iterator import (
    ITERABLE_KINDS,
    iterate_artifact_content,
    resolve_iterate_model,
)
from app.artifacts.service import ArtifactService
from app.artifacts.signing import SignedDownload, verify_download
from app.artifacts.storage import build_storage, safe_filename
from app.core.config import get_settings
from app.core.deps import DbSession, Org
from app.core.identity import get_org_context
from app.db.models import Artifact
from app.db.session import AsyncSessionLocal
from app.schemas.artifacts import (
    ArtifactDetail,
    ArtifactRead,
    ArtifactVersionRead,
    IterateRequest,
)

router = APIRouter(tags=["artifacts"])


def _service(db: AsyncSession, org_id: UUID) -> ArtifactService:
    """Build an :class:`ArtifactService` over the configured object storage."""
    settings = get_settings()
    return ArtifactService(db, build_storage(settings.ARTIFACTS_DIR), settings, org_id)


@asynccontextmanager
async def _download_session(org_id: UUID) -> AsyncGenerator[AsyncSession, None]:
    """Own an org-scoped session for a download (read-only; transaction-local GUC).

    A single SELECT under a transaction-local ``app.current_org`` (``is_local=true``):
    no commit, so the GUC is discarded on close and never leaks to the next pooled
    request — the read-path analogue of ``core.deps.get_db`` (R2).
    """
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("SELECT set_config('app.current_org', :org, true)"), {"org": str(org_id)}
        )
        yield session


def _resolve_access(
    artifact_id: UUID, request: Request, token: str | None
) -> tuple[UUID, SignedDownload | None]:
    """Resolve the download org from a signed token or the request context.

    A token wins when present and must match the path artifact (else 403); otherwise
    the standard org-context dependency applies. Returns ``(org_id, payload|None)``.
    """
    if token is not None:
        payload = verify_download(token, secret=get_settings().ARTIFACT_URL_SECRET)
        if payload is None or payload.artifact_id != artifact_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="invalid or expired download token"
            )
        return payload.org_id, payload
    org = get_org_context(
        request, request.headers.get("x-org-id"), request.headers.get("x-user-id")
    )
    return org.org_id, None


def _file_response(
    svc: ArtifactService, artifact: Artifact, *, content: str | None, storage_ref: str | None
) -> Response:
    """Stream an artifact snapshot's bytes as an attachment download (§12 Download)."""
    if artifact.status == "generating":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="artifact is still generating")
    if artifact.status == "failed":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"artifact generation failed: {artifact.error or 'unknown error'}",
        )
    try:
        data = svc.load_bytes(content=content, storage_ref=storage_ref)
    except FileNotFoundError as exc:
        # Row exists but the bytes are gone — surface honestly, don't 200 with empty.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="artifact bytes missing from storage"
        ) from exc

    filename = safe_filename(artifact.filename or str(artifact.id))
    return Response(
        content=data,
        media_type=artifact.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactRead])
async def list_run_artifacts(run_id: UUID, db: DbSession, org: Org) -> list[Artifact]:
    """List a run's artifacts, oldest first (§10/§14: the run lists them all)."""
    return list(await _service(db, org.org_id).list_for_run(run_id))


async def _build_detail(svc: ArtifactService, artifact: Artifact) -> ArtifactDetail:
    """Project an artifact + its versions + a fresh signed URL into the detail DTO (§10)."""
    versions = await svc.versions(artifact.id)
    base = ArtifactRead.model_validate(artifact).model_dump()
    return ArtifactDetail(
        **base,
        download_url=svc.signed_url(artifact),
        preview=artifact.content,  # inline text only; None for binary/storage-spilled
        versions=[ArtifactVersionRead.model_validate(v) for v in versions],
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactDetail)
async def get_artifact(artifact_id: UUID, db: DbSession, org: Org) -> ArtifactDetail:
    """Return one artifact's metadata, version list, and a fresh signed URL (§10/§12)."""
    svc = _service(db, org.org_id)
    artifact = await svc.get(artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="artifact not found")
    return await _build_detail(svc, artifact)


@router.post("/artifacts/{artifact_id}/iterate", response_model=ArtifactDetail)
async def iterate_artifact(
    artifact_id: UUID, payload: IterateRequest, db: DbSession, org: Org
) -> ArtifactDetail:
    """Revise an artifact per ``instruction`` → a new version (Canvas edit/refine, §10).

    Synchronous + atomic (see ARTIFACTS iterator note on the ``state_delta`` deviation):
    re-runs the producer agent's model on the current content, persists the result as
    the next immutable version (older versions stay downloadable), and returns the
    updated detail with the new ``current_version`` and a fresh signed URL.
    """
    svc = _service(db, org.org_id)
    artifact = await svc.get(artifact_id)
    if artifact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="artifact not found")
    if artifact.kind not in ITERABLE_KINDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"artifacts of kind '{artifact.kind}' cannot be iterated in v1 (text/code only)",
        )
    if artifact.status != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="artifact is not ready to iterate")

    # Read the current version's content (the durable snapshot), loading spilled text
    # from storage if it is not inlined.
    current = await svc.get_version(artifact_id, artifact.current_version)
    current_content = current.content if current is not None else artifact.content
    if current_content is None:
        storage_ref = current.storage_ref if current is not None else artifact.storage_ref
        if storage_ref is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="artifact content is unavailable to iterate"
            )
        try:
            current_content = svc.load_bytes(content=None, storage_ref=storage_ref).decode("utf-8")
        except (FileNotFoundError, UnicodeDecodeError) as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="artifact content could not be read to iterate"
            ) from exc

    model = await resolve_iterate_model(
        db,
        org_id=org.org_id,
        producer_agent_id=artifact.producer_agent_id,
        settings=get_settings(),
    )
    if model is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="no producer agent/model is available to iterate this artifact",
        )
    try:
        revised = await iterate_artifact_content(
            model=model,
            kind=artifact.kind,
            filename=artifact.filename,
            current_content=current_content,
            instruction=payload.instruction,
        )
    except Exception as exc:  # noqa: BLE001 — provider/model failure surfaced as 502 (logged).
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"iterate failed: {exc}") from exc

    await svc.add_version(artifact, content=revised)
    await db.commit()
    return await _build_detail(svc, artifact)


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: UUID, request: Request, token: str | None = None
) -> Response:
    """Download an artifact's current (or token-pinned) version (§10, RLS-scoped)."""
    org_id, payload = _resolve_access(artifact_id, request, token)
    async with _download_session(org_id) as db:
        svc = _service(db, org_id)
        artifact = await svc.get(artifact_id)
        if artifact is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="artifact not found")

        version_no = (
            payload.version
            if payload is not None and payload.version is not None
            else artifact.current_version
        )
        snapshot = await svc.get_version(artifact_id, version_no)
        # Prefer the durable snapshot; fall back to the artifact row's own pointers.
        content = snapshot.content if snapshot is not None else artifact.content
        storage_ref = snapshot.storage_ref if snapshot is not None else artifact.storage_ref
        return _file_response(svc, artifact, content=content, storage_ref=storage_ref)


@router.get("/artifacts/{artifact_id}/versions/{version}/download")
async def download_artifact_version(
    artifact_id: UUID, version: int, request: Request, token: str | None = None
) -> Response:
    """Download a specific historical version (§10, version switcher / Canvas history)."""
    org_id, payload = _resolve_access(artifact_id, request, token)
    if payload is not None and payload.version is not None and payload.version != version:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="token does not authorize this version"
        )
    async with _download_session(org_id) as db:
        svc = _service(db, org_id)
        artifact = await svc.get(artifact_id)
        if artifact is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="artifact not found")
        snapshot = await svc.get_version(artifact_id, version)
        if snapshot is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="artifact version not found")
        return _file_response(
            svc, artifact, content=snapshot.content, storage_ref=snapshot.storage_ref
        )
