"""Knowledge sources router (ARCH §14/§10.5, TECHNICAL §11.5).

Registers RAG sources under a team (team-shared or agent-private) and drives the
ingestion worker. Three write paths:

* ``POST /teams/{id}/knowledge`` — register a non-file source (url/db/team_doc) by
  reference; ingestion is spawned immediately (ITEM 2 root-cause #1: registration
  now actually triggers the worker).
* ``POST /teams/{id}/knowledge/upload`` — multipart **file** upload: the bytes are
  stored, a ``kind='file'`` source is created, and ingestion is spawned (root-cause
  #2: files now carry real bytes instead of a bare URI string).
* ``DELETE /teams/{id}/knowledge/{source_id}`` — soft-delete the source **and**
  hard-delete its vector chunks so retrieval never serves stale data.

Status (``pending → ingesting → ready|failed``) + ``chunk_count`` are written by the
worker (:mod:`app.knowledge.worker`); clients poll the list endpoint until terminal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, status

from app.core.config import get_settings
from app.core.deps import DbSession, Org
from app.db.models import KnowledgeSource, Team
from app.db.repositories import OrgScopedRepository
from app.knowledge.store import delete_source_vectors
from app.knowledge.worker import spawn_ingestion
from app.schemas.knowledge import KnowledgeSourceCreate, KnowledgeSourceRead

router = APIRouter(tags=["knowledge"])


async def _require_team(db: DbSession, org: Org, team_id: UUID) -> Team:
    team = await OrgScopedRepository(db, Team, org.org_id).get(team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="team not found")
    return team


@router.post(
    "/teams/{team_id}/knowledge",
    response_model=KnowledgeSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_source(
    team_id: UUID, payload: KnowledgeSourceCreate, db: DbSession, org: Org, request: Request
) -> KnowledgeSource:
    """Register a by-reference RAG source (url/db/team_doc) and start ingestion (ARCH §10.5.1).

    File sources use the multipart ``/upload`` endpoint instead (they need bytes, not
    a URI string — ITEM 2 root-cause #2). Ingestion is spawned after commit so the
    background worker sees the committed row.
    """
    await _require_team(db, org, team_id)
    source = KnowledgeSource(
        org_id=org.org_id,
        team_id=team_id,
        agent_id=payload.agent_id,
        kind=payload.kind,
        uri=payload.uri,
        display_name=payload.display_name,
        connector_config=(
            payload.connector_config.model_dump() if payload.connector_config else None
        ),
        created_by=org.user_id,
    )
    saved = await OrgScopedRepository(db, KnowledgeSource, org.org_id).add(source)
    await db.commit()  # commit before spawning so the worker's own session sees the row
    spawn_ingestion(request.app, source_id=saved.id, org_id=org.org_id)
    return saved


@router.post(
    "/teams/{team_id}/knowledge/upload",
    response_model=KnowledgeSourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_knowledge_file(
    team_id: UUID,
    db: DbSession,
    org: Org,
    request: Request,
    file: UploadFile,
    agent_id: Annotated[UUID | None, Form()] = None,
    display_name: Annotated[str | None, Form()] = None,
) -> KnowledgeSource:
    """Upload a file as a knowledge source and start ingestion (ARCH §10.5.1).

    The bytes are stored under the knowledge object-storage root; a ``kind='file'``
    source records the storage path and starts ``pending``. The universal loader
    routes by file format at ingest time (any extension — ITEM 2). Oversized uploads
    are rejected at the boundary (R5: validate input, fail fast)."""
    await _require_team(db, org, team_id)
    settings = get_settings()

    data = await file.read()
    if len(data) > settings.KNOWLEDGE_MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file exceeds the {settings.KNOWLEDGE_MAX_UPLOAD_BYTES}-byte upload limit",
        )

    safe_name = Path(file.filename or "upload").name  # strip any path components
    base = Path(settings.KNOWLEDGE_FILES_DIR) / str(org.org_id) / str(team_id)
    base.mkdir(parents=True, exist_ok=True)
    dest = base / f"{uuid4().hex}_{safe_name}"
    dest.write_bytes(data)

    source = KnowledgeSource(
        org_id=org.org_id,
        team_id=team_id,
        agent_id=agent_id,
        kind="file",
        uri=str(dest),
        display_name=display_name or safe_name,
        created_by=org.user_id,
    )
    saved = await OrgScopedRepository(db, KnowledgeSource, org.org_id).add(source)
    await db.commit()
    spawn_ingestion(request.app, source_id=saved.id, org_id=org.org_id)
    return saved


@router.get("/teams/{team_id}/knowledge", response_model=list[KnowledgeSourceRead])
async def list_knowledge_sources(team_id: UUID, db: DbSession, org: Org) -> list[KnowledgeSource]:
    """List a team's knowledge sources with live status + chunk_count (ARCH §14).

    Clients poll this until each source reaches a terminal status (``ready``/``failed``).
    """
    return list(await OrgScopedRepository(db, KnowledgeSource, org.org_id).list(team_id=team_id))


@router.delete("/teams/{team_id}/knowledge/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_source(team_id: UUID, source_id: UUID, db: DbSession, org: Org) -> None:
    """Soft-delete a source AND hard-delete its vector chunks (ARCH §10.5, ITEM 2).

    Removing the chunks (by ``source_id`` metadata) in the same transaction means a
    deleted source can never be served by ``search_knowledge`` again — no stale RAG.
    """
    repo = OrgScopedRepository(db, KnowledgeSource, org.org_id)
    source = await repo.get(source_id)
    if source is None or source.team_id != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="knowledge source not found")

    await delete_source_vectors(db, source_id=source_id, org_id=org.org_id)
    await repo.soft_delete(source_id)
