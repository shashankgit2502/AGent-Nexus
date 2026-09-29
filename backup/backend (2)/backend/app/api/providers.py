"""Settings → AI Providers router: connections / catalog / profiles (ARCH §14/§9/§27).

CRUD for the Model Resolution Layer. The validation probe (ARCH §27.3) and model
discovery (ARCH §27.2) are wired in their own services (Step 3); this router is the
REST surface over the three tables (TECHNICAL §11.3).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import update

from app.core.config import get_settings
from app.core.deps import DbSession, Org
from app.core.secrets import SecretNotFound, build_secret_resolver
from app.db.models import Agent, InferenceProfile, LLMConnection, ModelCatalog
from app.db.repositories import OrgScopedRepository
from app.models_layer.base_url import canonical_base_url
from app.models_layer.connections import WORKBENCH_METADATA_KEYS
from app.models_layer.discovery import DiscoveredModel, discover_models
from app.models_layer.loader import load_conn_cat_repos
from app.models_layer.profiles import InMemoryProfileRepository
from app.models_layer.resolver import ModelResolver
from app.models_layer.validation import probe_model
from app.schemas.providers import (
    CatalogModelCreate,
    CatalogModelRead,
    CatalogModelUpdate,
    CatalogPage,
    ConnectionCreate,
    ConnectionRead,
    ConnectionTestResult,
    ConnectionUpdate,
    ProfileCreate,
    ProfileRead,
    ProfileUpdate,
)

router = APIRouter(prefix="/providers", tags=["providers"])


def _workbench_metadata(payload: Any, *, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Project the flat Workbench fields of a payload into ``config_metadata``.

    The DTO is flat (one field per gateway setting) because that is what a form
    submits; the column is JSONB because gateway header sets are open-ended. This
    is the single translation between the two, so the writer here and the reader
    in :meth:`app.models_layer.connections.LLMConnection.workbench` cannot drift.

    ``exclude_unset`` semantics are preserved: a key absent from the payload
    leaves any existing value alone, and an explicit ``null`` clears it. Keys the
    payload does not own are never touched, so a future non-Workbench setting
    sharing the column survives an edit.
    """
    merged = dict(existing or {})
    supplied = payload.model_dump(exclude_unset=True)
    for key in WORKBENCH_METADATA_KEYS:
        if key not in supplied:
            continue
        value = supplied[key]
        if value in (None, ""):
            merged.pop(key, None)
        else:
            merged[key] = str(value).strip()
    return merged


def _to_connection_read(conn: LLMConnection) -> ConnectionRead:
    """Flatten a connection row (incl. ``config_metadata``) into the read DTO.

    Done explicitly rather than by ORM attribute mapping because the gateway
    fields live inside JSONB — without this the edit form would open blank and a
    save would silently wipe the charge code.
    """
    meta = conn.config_metadata or {}
    return ConnectionRead.model_validate(
        {
            **{c.name: getattr(conn, c.name) for c in conn.__table__.columns},
            **{key: meta.get(key) for key in WORKBENCH_METADATA_KEYS},
        }
    )


async def _probe_workbench(
    conn: LLMConnection, db: DbSession
) -> tuple[bool, str, list[DiscoveredModel]]:
    """Validate a Workbench connection by invoking a model registered against it.

    The gateway exposes deployment-scoped routes only, so there is no model list
    to call. ARCH §27.3 accepts either form of probe ("a 1-token completion **or**
    ``models.list``"), so we take the other one: resolve the first enabled chat
    model on this connection and send it a trivial prompt. That exercises the
    whole path the runtime uses — base URL, deployment, subscription header,
    charge code, api-version — which a list call never would.

    Returns ``(ok, detail, [])``. The model list is always empty: this probe
    validates, it does not discover (R3 — no invented list endpoint).
    """
    catalog_repo = OrgScopedRepository(db, ModelCatalog, conn.org_id)
    candidates = [
        m
        for m in await catalog_repo.list(provider_connection_id=conn.id, model_type="chat")
        if m.enabled
    ]
    if not candidates:
        return (
            False,
            (
                "No model registered for this Workbench connection yet. Add one in "
                "the catalog with its deployment name, then test again."
            ),
            [],
        )

    target = candidates[0]
    resolver = await _resolver_for(db, conn.org_id)
    try:
        # ``require_tools=False``: the probe proves reachability and credentials,
        # not mesh eligibility — that is the catalog's ``supports_tools`` flag.
        model = resolver.resolve_catalog_model(target.id, require_tools=False)
    except Exception as exc:  # noqa: BLE001 — a build error is a probe failure, reported
        return False, f"{type(exc).__name__}: {exc}", []

    # ``probe_model`` is a blocking provider call; off-thread so it cannot stall
    # the event loop for the request timeout.
    result = await asyncio.to_thread(probe_model, model)
    detail = f"Reachable via {target.display_name}" if result.ok else result.detail
    return result.ok, detail, []


async def _resolver_for(db: DbSession, org_id: UUID) -> ModelResolver:
    """A ModelResolver over the org's live model layer, for API-side probes.

    Reuses the same snapshot loader the runtime uses so a connection is tested
    through *exactly* the construction an agent turn would perform — the failure
    mode this avoids is a credential that passes its own test and then fails in a
    run because the two paths built it differently.
    """
    conn_repo, cat_repo = await load_conn_cat_repos(db, org_id=org_id)
    return ModelResolver(
        connections=conn_repo,
        catalog=cat_repo,
        # No profile is involved in a bare-catalog probe; an empty repo is enough.
        profiles=InMemoryProfileRepository([]),
        secrets=build_secret_resolver(get_settings()),
    )


async def _probe_connection(
    conn: LLMConnection, db: DbSession
) -> tuple[bool, str, list[DiscoveredModel]]:
    """Run the discovery/validation probe for a connection (ARCH §27.2/§27.3).

    Resolves the connection's ``api_key_ref`` to a usable key (local raw keys are
    honoured in dev, Bug 5) and lists the provider's models *with* their advertised
    capabilities. Returns ``(ok, detail, models)``. A missing/unresolvable key is a
    probe failure, not an exception, so the caller can surface it to the UI (R3).
    """
    settings = get_settings()
    secrets = build_secret_resolver(settings)
    try:
        api_key = secrets.resolve(conn.api_key_ref)
    except SecretNotFound as exc:
        return False, str(exc), []
    if conn.provider == "workbench":
        # The gateway serves deployment-scoped routes only — there is no model
        # list to call — so it is validated the other way ARCH §27.3 allows: a
        # cheap completion against a model the user has already registered.
        return await _probe_workbench(conn, db)
    result = await discover_models(
        provider=conn.provider,
        base_url=conn.base_url,
        api_key=api_key,
        api_version=conn.api_version,
        # Local dev permits private hosts (e.g. an Ollama at localhost:11434).
        allow_private=settings.is_local,
    )
    return result.ok, result.detail, result.models


# ── Connections (Layer 1) ─────────────────────────────────────────────────────
@router.post("/connections", response_model=ConnectionRead, status_code=status.HTTP_201_CREATED)
async def create_connection(payload: ConnectionCreate, db: DbSession, org: Org) -> ConnectionRead:
    """Register a provider connection (ARCH §27.1). Stores an ``api_key_ref`` only."""
    conn = LLMConnection(
        org_id=org.org_id,
        created_by=org.user_id,
        display_name=payload.display_name,
        provider=payload.provider,
        # Store the API root, not a pasted chat/completions endpoint (Bug 5), so the
        # OpenAI-compatible client doesn't double-append the operation path.
        base_url=canonical_base_url(payload.base_url),
        api_key_ref=payload.api_key_ref,
        api_version=payload.api_version,
        scope=payload.scope,
        team_id=payload.team_id,
        # Gateway settings (Workbench). Empty for every other provider, so the
        # column stays '{}' exactly as the server default would have left it.
        config_metadata=_workbench_metadata(payload),
    )
    saved = await OrgScopedRepository(db, LLMConnection, org.org_id).add(conn)
    return _to_connection_read(saved)


@router.get("/connections", response_model=list[ConnectionRead])
async def list_connections(db: DbSession, org: Org) -> list[ConnectionRead]:
    """List the org's provider connections (ARCH §14)."""
    rows = await OrgScopedRepository(db, LLMConnection, org.org_id).list()
    return [_to_connection_read(row) for row in rows]


@router.put("/connections/{connection_id}", response_model=ConnectionRead)
async def update_connection(
    connection_id: UUID, payload: ConnectionUpdate, db: DbSession, org: Org
) -> ConnectionRead:
    """Edit a connection (Bug 5 edit button). Re-sets ``validated_at`` to NULL when
    the key/endpoint change, since the prior validation no longer applies."""
    repo = OrgScopedRepository(db, LLMConnection, org.org_id)
    conn = await repo.get(connection_id)
    if conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")

    changes = payload.model_dump(exclude_unset=True)
    if "base_url" in changes:
        changes["base_url"] = canonical_base_url(changes["base_url"])
    # The gateway fields are not columns — they are merged into config_metadata
    # below, so they must not be setattr'd onto the row.
    gateway_changed = bool(set(WORKBENCH_METADATA_KEYS) & changes.keys())
    for field in WORKBENCH_METADATA_KEYS:
        changes.pop(field, None)

    revalidating_fields = {"provider", "base_url", "api_key_ref", "api_version"}
    for field, value in changes.items():
        setattr(conn, field, value)
    if gateway_changed:
        # Reassigned (not mutated in place) so SQLAlchemy sees the JSONB change —
        # an in-place dict edit on a JSONB column is not tracked and would be
        # silently dropped on flush.
        conn.config_metadata = _workbench_metadata(payload, existing=conn.config_metadata)
    if revalidating_fields & changes.keys() or gateway_changed:
        conn.validated_at = None  # stale validation; user re-tests

    await db.flush()
    await db.refresh(conn)
    return _to_connection_read(conn)


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(connection_id: UUID, db: DbSession, org: Org) -> None:
    """Soft-delete a connection (Bug 5 delete button). Cascades to its catalog
    models via FK ``ON DELETE CASCADE`` only on hard delete; soft-delete here
    hides the connection while preserving derived rows for audit."""
    repo = OrgScopedRepository(db, LLMConnection, org.org_id)
    if not await repo.soft_delete(connection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")


@router.post("/connections/{connection_id}/test", response_model=ConnectionTestResult)
async def test_connection(connection_id: UUID, db: DbSession, org: Org) -> ConnectionTestResult:
    """Run the validation probe on demand (Bug 5 test button, ARCH §27.3).

    On success marks the connection ``validated`` (clears the stuck-pending state);
    on failure returns the provider/network error detail so the user sees *why*
    (the original bug: it silently stayed pending with no error)."""
    repo = OrgScopedRepository(db, LLMConnection, org.org_id)
    conn = await repo.get(connection_id)
    if conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")

    ok, detail, models = await _probe_connection(conn, db)
    if ok:
        conn.validated_at = datetime.now(UTC)
        conn.last_sync_at = conn.validated_at
        await db.flush()
        await db.refresh(conn)
    return ConnectionTestResult(
        ok=ok, detail=detail, models_found=len(models), validated_at=conn.validated_at
    )


@router.post("/connections/{connection_id}/discover", response_model=list[CatalogModelRead])
async def discover_connection_models(
    connection_id: UUID, db: DbSession, org: Org
) -> list[ModelCatalog]:
    """Auto-discover models and sync the catalog with their capabilities (ARCH §14/§27.2).

    Doubles as a validation probe (marks the connection validated on success). Each
    discovered model carries the capabilities the provider advertises (OpenRouter
    exposes ``supported_parameters``/``architecture`` inline, so ``supports_tools``
    — the §9.3 hard gate — is set honestly). New ids are inserted; **existing rows
    are updated** so a re-discover corrects capability flags that an older,
    capability-blind discovery left at the ``false`` default (idempotent upsert)."""
    conn_repo = OrgScopedRepository(db, LLMConnection, org.org_id)
    conn = await conn_repo.get(connection_id)
    if conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")

    ok, detail, models = await _probe_connection(conn, db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)

    conn.validated_at = datetime.now(UTC)
    conn.last_sync_at = conn.validated_at

    catalog_repo = OrgScopedRepository(db, ModelCatalog, org.org_id)
    existing: dict[str, ModelCatalog] = {
        m.model_identifier: m for m in await catalog_repo.list(provider_connection_id=connection_id)
    }
    synced: list[ModelCatalog] = []
    for dm in models:
        row = existing.get(dm.id)
        if row is None:
            row = ModelCatalog(
                org_id=org.org_id,
                provider_connection_id=connection_id,
                display_name=dm.id,
                model_identifier=dm.id,
                # Classified from the id (Approach B) instead of hardcoding 'chat',
                # so discovered embedding models land as embeddings. On re-discover we
                # deliberately do NOT touch model_type below — a manual reclassification
                # (PATCH /catalog/{id}) must stick.
                model_type=dm.model_type,
                supports_tools=dm.supports_tools,
                supports_streaming=True,
                supports_vision=dm.supports_vision,
                supports_reasoning=dm.supports_reasoning,
                context_window=dm.context_window,
                source="discovered",
            )
            synced.append(await catalog_repo.add(row))
        else:
            # Upsert: refresh advertised capabilities on the existing row so a
            # re-discover heals rows seeded before discovery read capabilities.
            row.supports_tools = dm.supports_tools
            row.supports_vision = dm.supports_vision
            row.supports_reasoning = dm.supports_reasoning
            if dm.context_window is not None:
                row.context_window = dm.context_window
            synced.append(row)
    await db.flush()
    return synced


@router.get("/connections/{connection_id}/models", response_model=CatalogPage)
async def list_connection_models(
    connection_id: UUID,
    db: DbSession,
    org: Org,
    q: str | None = None,
    supports_tools: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CatalogPage:
    """List one connection's catalog models — org-scoped, searchable, paginated (ARCH §14).

    Master-detail backing for Settings→AI: rather than one flat whole-org catalog
    (the old ``GET /catalog`` that rendered every model in a single scroll), the UI
    lazy-loads a connection's models on expand. ``q`` matches the display name or
    model identifier (case-insensitive); ``supports_tools`` narrows to the §9.3
    mesh-eligible set. Returns 404 when the connection isn't in this org — checked
    explicitly *and* enforced by RLS (defence-in-depth, §11.7)."""
    conn_repo = OrgScopedRepository(db, LLMConnection, org.org_id)
    if await conn_repo.get(connection_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")

    eq_filters: dict[str, Any] = {"provider_connection_id": connection_id}
    if supports_tools is not None:
        eq_filters["supports_tools"] = supports_tools

    repo = OrgScopedRepository(db, ModelCatalog, org.org_id)
    items, total = await repo.search_page(
        search=q,
        search_columns=("display_name", "model_identifier"),
        limit=limit,
        offset=offset,
        order_by="created_at",
        **eq_filters,
    )
    return CatalogPage(
        items=[CatalogModelRead.model_validate(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── Catalog (Layer 2) ─────────────────────────────────────────────────────────
@router.post("/catalog", response_model=CatalogModelRead, status_code=status.HTTP_201_CREATED)
async def create_catalog_model(
    payload: CatalogModelCreate, db: DbSession, org: Org
) -> ModelCatalog:
    """Manually register a catalog model (ARCH §27.2). ``supports_tools`` gates mesh use.

    The catalog enforces one *live* row per ``(connection, model_identifier)`` via the
    partial unique index ``uq_catalog_model`` (``deleted_at IS NULL`` only). A blind
    insert of an already-registered model raised an asyncpg ``UniqueViolationError`` that
    surfaced as an opaque 500 (the UI's "Failed to fetch", since the error path skips
    CORS). We pre-check for an existing live row and return a clear **409** instead —
    mirroring the partial index exactly (a previously soft-deleted model can be re-added)
    and matching the conflict policy used by ``delete_profile`` (R3: clean boundary error,
    not a band-aid; ``/discover`` already UPSERTs, the manual path must not duplicate)."""
    repo = OrgScopedRepository(db, ModelCatalog, org.org_id)
    if await repo.list(
        provider_connection_id=payload.provider_connection_id,
        model_identifier=payload.model_identifier,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="model already registered for this connection",
        )
    model = ModelCatalog(
        org_id=org.org_id,
        provider_connection_id=payload.provider_connection_id,
        display_name=payload.display_name,
        model_identifier=payload.model_identifier,
        model_type=payload.model_type,
        deployment_name=payload.deployment_name,
        supports_tools=payload.supports_tools,
        supports_streaming=payload.supports_streaming,
        supports_vision=payload.supports_vision,
        supports_reasoning=payload.supports_reasoning,
        context_window=payload.context_window,
        model_family=payload.model_family,
        source=payload.source,
    )
    return await repo.add(model)


@router.patch("/catalog/{model_id}", response_model=CatalogModelRead)
async def update_catalog_model(
    model_id: UUID, payload: CatalogModelUpdate, db: DbSession, org: Org
) -> ModelCatalog:
    """Edit a catalog model — chiefly to reclassify ``model_type`` (Approach B).

    Discovery classifies chat vs embedding from the id (best-effort), so a model can
    land mislabeled; this lets the user flip it (e.g. ``nemotron:embed`` chat→embedding)
    so it shows in the team embedding picker, without a delete + re-add. Reclassifying
    to ``embedding`` also clears ``supports_tools`` — embeddings are not tool-callers
    (mirrors the Add-model form rule, §9.3)."""
    repo = OrgScopedRepository(db, ModelCatalog, org.org_id)
    model = await repo.get(model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model not found")

    fields = payload.model_dump(exclude_unset=True)
    for name, value in fields.items():
        setattr(model, name, value)
    if fields.get("model_type") == "embedding":
        model.supports_tools = False
    await db.flush()
    await db.refresh(model)
    return model


@router.get("/catalog", response_model=list[CatalogModelRead])
async def list_catalog(
    db: DbSession, org: Org, supports_tools: bool | None = None
) -> list[ModelCatalog]:
    """List catalog models; ``?supports_tools=true`` filters to mesh-eligible (ARCH §9.3)."""
    repo = OrgScopedRepository(db, ModelCatalog, org.org_id)
    if supports_tools is None:
        return list(await repo.list())
    return list(await repo.list(supports_tools=supports_tools))


@router.delete("/catalog/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog_model(model_id: UUID, db: DbSession, org: Org) -> None:
    """Soft-delete a catalog model (Bug 5 — delete option for a model)."""
    repo = OrgScopedRepository(db, ModelCatalog, org.org_id)
    if not await repo.soft_delete(model_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="model not found")


# ── Profiles (Layer 3) ────────────────────────────────────────────────────────
async def _clear_default_profile(db: DbSession, org: Org, *, keep: UUID | None = None) -> None:
    """Unset every other live default profile for the org (single-default invariant).

    The database enforces the invariant with a partial unique index, so without this
    the *second* default would fail on insert. Clearing first makes "set default" a
    normal user action rather than an error the UI has to explain.
    """
    await db.execute(
        update(InferenceProfile)
        .where(
            InferenceProfile.org_id == org.org_id,
            InferenceProfile.is_default.is_(True),
            InferenceProfile.deleted_at.is_(None),
            *([InferenceProfile.id != keep] if keep is not None else []),
        )
        .values(is_default=False)
    )
    await db.flush()


@router.post("/profiles", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(payload: ProfileCreate, db: DbSession, org: Org) -> InferenceProfile:
    """Create an inference profile (ARCH §27.4).

    ``is_default`` marks this as the org's whole-run reasoning profile — the model the
    Orchestrator's planner and the Synthesizer use (ARCH §4.1/§4.6). Any previous
    default is cleared first so the single-default invariant holds.
    """
    if payload.is_default:
        await _clear_default_profile(db, org)
    profile = InferenceProfile(
        org_id=org.org_id,
        name=payload.name,
        default_model_id=payload.default_model_id,
        temperature=payload.temperature,
        top_p=payload.top_p,
        max_tokens=payload.max_tokens,
        reasoning_level=payload.reasoning_level,
        verbosity=payload.verbosity,
        json_mode=payload.json_mode,
        streaming=payload.streaming,
        is_default=payload.is_default,
    )
    return await OrgScopedRepository(db, InferenceProfile, org.org_id).add(profile)


@router.patch("/profiles/{profile_id}", response_model=ProfileRead)
async def update_profile(
    profile_id: UUID, payload: ProfileUpdate, db: DbSession, org: Org
) -> InferenceProfile:
    """Partially update a profile — notably, select it as the org default (ARCH §14).

    Only fields present in the request change. Setting ``is_default=true`` clears the
    previous default in the same transaction; setting it ``false`` simply unsets this
    one, which leaves the org with no default (the orchestration model then falls back
    to the strongest model on the team's roster — see ``select_orchestration_ref``).
    """
    repo = OrgScopedRepository(db, InferenceProfile, org.org_id)
    profile = await repo.get(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")

    fields = payload.model_dump(exclude_unset=True)
    if fields.get("is_default") is True:
        await _clear_default_profile(db, org, keep=profile_id)
    for name, value in fields.items():
        setattr(profile, name, value)
    await db.flush()
    return profile


@router.get("/profiles", response_model=list[ProfileRead])
async def list_profiles(db: DbSession, org: Org) -> list[InferenceProfile]:
    """List the org's inference profiles (ARCH §14)."""
    return list(await OrgScopedRepository(db, InferenceProfile, org.org_id).list())


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: UUID, db: DbSession, org: Org) -> None:
    """Soft-delete an inference profile (ARCH §14). Blocks if agents still use it.

    Agents select a model bundle via ``agents.profile_id`` (TECHNICAL §11.2). Deleting
    a profile out from under a live agent would orphan its model selection, so per the
    locked policy we **block with 409** and return the referencing agents — the UI
    guides the user to reassign them first. We never null an agent's profile silently
    (R3: integrity over a convenient band-aid)."""
    repo = OrgScopedRepository(db, InferenceProfile, org.org_id)
    if await repo.get(profile_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")

    agents = await OrgScopedRepository(db, Agent, org.org_id).list(profile_id=profile_id)
    if agents:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "profile is in use by agents; reassign them before deleting",
                "agents": [{"id": str(a.id), "name": a.name} for a in agents],
            },
        )
    await repo.soft_delete(profile_id)
