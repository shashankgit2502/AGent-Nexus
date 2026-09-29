"""Resolve which embedding model a knowledge source is ingested/retrieved with.

ITEM 2 root-cause #3: a team/agent had no embedding model, so ingestion had
nothing to embed with and sources hung at ``pending``. This module is the **runtime
selection** layer (ARCH §9.5): it maps a source *owner* to a ``model_catalog``
embedding-model id, using the locked resolution chain

    agent.embedding_model_id  (agent-private override)
      → team.embedding_model_id
        → the org default embedding model

The org default is, by convention, the org's single enabled ``model_type='embedding'``
catalog row — explicit per-team/agent selection overrides it. If **nothing** resolves,
we raise :class:`NoEmbeddingModelConfigured` so the worker can mark the source
``failed`` with a precise reason instead of hanging silently (R3).

Selection is pure-ish DB reads (no embedding client built here); turning the chosen
id into a live ``Embeddings`` is :class:`~app.models_layer.embeddings.EmbeddingsResolver`'s
job. Keeping them separate lets the worker resolve the *id* (and thus the pgvector
collection key, §9.5) without constructing a client until it actually embeds.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, LLMConnection, ModelCatalog, Team
from app.models_layer.errors import ModelResolutionError, NotAnEmbeddingModel


class NoEmbeddingModelConfigured(ModelResolutionError):
    """No embedding model resolves for a source's owner (agent → team → org default).

    Carried to the worker so the source becomes ``failed`` with this message — the
    honest replacement for the old silent ``pending`` (ITEM 2 RCA #3).
    """

    def __init__(self, *, team_id: UUID | None, agent_id: UUID | None) -> None:
        # team_id may be None for a no-team conversation attachment (§8.5.3): nothing
        # in the chain (no agent, no team, no org default) resolved an embedding model.
        scope = (
            f"agent {agent_id}"
            if agent_id
            else f"team {team_id}"
            if team_id
            else "this conversation"
        )
        super().__init__(
            f"no embedding model configured for {scope}; set one on the agent or team, "
            "or add an org default embedding model (Settings → AI), then re-ingest"
        )
        self.team_id = team_id
        self.agent_id = agent_id


async def _org_default_embedding_model_id(db: AsyncSession, org_id: UUID) -> UUID | None:
    """The org's default embedding model: its single enabled embedding catalog row.

    Convention (no separate "is_default" flag in v1): an org configures exactly one
    enabled ``model_type='embedding'`` model, which becomes the default. If several
    exist we pick the oldest (deterministic) — explicit team/agent selection is the
    way to choose among many, so this is only the last-resort fallback.
    """
    # Join the owning connection and require it live: a catalog row whose connection
    # was soft-deleted is an *orphan* — still ``deleted_at IS NULL`` itself (connection
    # soft-delete preserves derived rows for audit, providers.delete_connection) but
    # unresolvable, because the resolver snapshot drops soft-deleted connections. Picking
    # one would raise ``EntityNotFound`` mid-ingest (the orphan RCA). Only a model
    # reachable through a live connection is a usable default.
    stmt = (
        select(ModelCatalog.id)
        .join(LLMConnection, ModelCatalog.provider_connection_id == LLMConnection.id)
        .where(
            ModelCatalog.org_id == org_id,
            ModelCatalog.model_type == "embedding",
            ModelCatalog.enabled.is_(True),
            ModelCatalog.deleted_at.is_(None),
            LLMConnection.deleted_at.is_(None),
        )
        .order_by(ModelCatalog.created_at.asc())
        .limit(1)
    )
    result: UUID | None = await db.scalar(stmt)
    return result


async def org_default_vision_model_id(db: AsyncSession, org_id: UUID) -> UUID | None:
    """The org's default vision model: its oldest enabled ``supports_vision`` chat model.

    Used by the ingestion worker to caption images (ITEM 2 Slice C). ``None`` → no
    vision model configured; image content then relies on OCR alone (or, with neither,
    an image-only source fails with a clear reason). Convention-based like the default
    embedding model — explicit per-source vision selection isn't needed in v1.
    """
    # Live-connection join — see ``_org_default_embedding_model_id``: an orphaned vision
    # row (connection soft-deleted) must not be chosen, else ``resolve_catalog_model``
    # raises ``EntityNotFound`` and the whole ingest fails (this was the reported crash).
    stmt = (
        select(ModelCatalog.id)
        .join(LLMConnection, ModelCatalog.provider_connection_id == LLMConnection.id)
        .where(
            ModelCatalog.org_id == org_id,
            ModelCatalog.model_type == "chat",
            ModelCatalog.supports_vision.is_(True),
            ModelCatalog.enabled.is_(True),
            ModelCatalog.deleted_at.is_(None),
            LLMConnection.deleted_at.is_(None),
        )
        .order_by(ModelCatalog.created_at.asc())
        .limit(1)
    )
    result: UUID | None = await db.scalar(stmt)
    return result


async def _validated_embedding_choice(
    db: AsyncSession, *, org_id: UUID, model_id: UUID
) -> UUID | None:
    """Validate an **explicit** (agent/team) embedding selection (Approach B, Slice 3).

    Returns the id when it points at a live ``model_type='embedding'`` catalog row;
    raises :class:`NotAnEmbeddingModel` when the row exists but is the wrong type — the
    user's "you selected a non-embedding model" error, surfaced at ingest rather than
    letting ``init_embeddings`` fail opaquely or silently embedding with a chat model.
    Returns ``None`` when the selected row no longer exists (soft-deleted) **or its
    connection was soft-deleted** (an orphan — see ``_org_default_embedding_model_id``),
    so the chain falls through to the next level instead of using an unresolvable id.
    """
    row = (
        await db.execute(
            select(ModelCatalog.model_type, ModelCatalog.display_name)
            .join(LLMConnection, ModelCatalog.provider_connection_id == LLMConnection.id)
            .where(
                ModelCatalog.id == model_id,
                ModelCatalog.org_id == org_id,
                ModelCatalog.deleted_at.is_(None),
                LLMConnection.deleted_at.is_(None),
            )
        )
    ).first()
    if row is None:
        return None
    model_type, display_name = row
    if model_type != "embedding":
        raise NotAnEmbeddingModel(display_name)
    return model_id


async def resolve_embedding_model_id(
    db: AsyncSession,
    *,
    org_id: UUID,
    team_id: UUID | None,
    agent_id: UUID | None,
) -> UUID:
    """Return the embedding ``model_catalog`` id for a source owned by this team/agent.

    Chain (first hit wins): agent override → team setting → org default. Only live,
    org-scoped rows are considered (defence-in-depth alongside RLS, §11.7). An explicit
    agent/team selection is **type-validated**: if it points at a non-embedding model,
    we fail loudly (Approach B, Slice 3) rather than embed with the wrong model.

    ``team_id`` may be ``None`` for a **no-team conversation attachment** (ARCH §8.5.3):
    there is no agent/team selection, so resolution falls straight to the org default.

    Raises:
        NotAnEmbeddingModel: an explicit selection is not ``model_type='embedding'``.
        NoEmbeddingModelConfigured: nothing in the chain resolves — the worker turns
            either error into a ``failed`` status with the message, never a silent hang.
    """
    if agent_id is not None:
        agent_choice = await db.scalar(
            select(Agent.embedding_model_id).where(
                Agent.id == agent_id,
                Agent.org_id == org_id,
                Agent.deleted_at.is_(None),
            )
        )
        if agent_choice is not None:
            validated = await _validated_embedding_choice(db, org_id=org_id, model_id=agent_choice)
            if validated is not None:
                return validated

    if team_id is not None:
        team_choice = await db.scalar(
            select(Team.embedding_model_id).where(
                Team.id == team_id,
                Team.org_id == org_id,
                Team.deleted_at.is_(None),
            )
        )
        if team_choice is not None:
            validated = await _validated_embedding_choice(db, org_id=org_id, model_id=team_choice)
            if validated is not None:
                return validated

    org_default = await _org_default_embedding_model_id(db, org_id)
    if org_default is not None:
        return org_default

    raise NoEmbeddingModelConfigured(team_id=team_id, agent_id=agent_id)
