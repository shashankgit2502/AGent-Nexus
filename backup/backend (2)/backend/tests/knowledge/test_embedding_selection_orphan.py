"""Regression: orphaned catalog rows (connection soft-deleted) must not be selected.

RCA — ``providers.delete_connection`` soft-deletes a connection but **keeps its
``model_catalog`` rows** (for audit). The resolver snapshot, however, drops
soft-deleted connections (``agents.snapshot._build_resolver``), so those still-live
catalog rows become **orphans**: selectable but unresolvable. The org-default
vision/embedding selectors used to pick one, then ``resolve_catalog_model`` raised
``EntityNotFound`` and crashed the whole ingest (the reported bug). Selection now joins
the owning connection and requires it live.

Driven directly against Postgres in a throwaway org (``organizations`` is the RLS-free
tenant root) so the org-wide "oldest model" ordering is deterministic regardless of the
rows other integration tests leave behind. Skips where there is no DB (``integration``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import LLMConnection, ModelCatalog, Organization, Team
from app.knowledge.embedding_selection import (
    NoEmbeddingModelConfigured,
    org_default_vision_model_id,
    resolve_embedding_model_id,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """A session on a throwaway ``NullPool`` engine, disposed within this test's event
    loop — the shared app engine would otherwise retain a pooled asyncpg connection
    across pytest-asyncio's per-test loops ("Event loop is closed" on teardown)."""
    engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def _seed_org(db: AsyncSession) -> Organization:
    """Create an isolated org and bind the RLS GUC to it for the tenant inserts below."""
    org = Organization(name="Orphan RCA", slug=f"orphan-{uuid4().hex[:8]}")
    db.add(org)
    await db.flush()
    await db.execute(
        text("SELECT set_config('app.current_org', :o, false)"), {"o": str(org.id)}
    )
    return org


def _conn(org: Organization) -> LLMConnection:
    return LLMConnection(
        org_id=org.id,
        display_name="conn",
        provider="openai_compatible",
        base_url="https://provider.test/v1",
        api_key_ref="sk-test",
    )


def _catalog(
    org: Organization, conn_id: object, *, model_type: str, **flags: object
) -> ModelCatalog:
    return ModelCatalog(
        org_id=org.id,
        provider_connection_id=conn_id,
        display_name=model_type,
        model_identifier=f"{model_type}-{uuid4().hex[:6]}",
        model_type=model_type,
        source="manual",
        **flags,
    )


async def test_org_default_vision_skips_orphaned_connection(db: AsyncSession) -> None:
    org = await _seed_org(db)
    dead = _conn(org)
    db.add(dead)
    await db.flush()
    vision = _catalog(org, dead.id, model_type="chat", supports_vision=True)
    db.add(vision)
    await db.flush()

    # Soft-delete the connection → vision row is now an orphan (live row, dead conn).
    dead.deleted_at = datetime.now(UTC)
    await db.flush()

    # Pre-fix this returned vision.id (→ EntityNotFound mid-ingest); now skipped.
    assert await org_default_vision_model_id(db, org.id) is None
    await db.rollback()


async def test_org_default_vision_returns_model_on_live_connection(db: AsyncSession) -> None:
    """Positive control: the live-connection join must not over-filter — a vision model
    on a *live* connection is still selected as the org default."""
    org = await _seed_org(db)
    live = _conn(org)
    db.add(live)
    await db.flush()
    vision = _catalog(org, live.id, model_type="chat", supports_vision=True)
    db.add(vision)
    await db.flush()

    assert await org_default_vision_model_id(db, org.id) == vision.id
    await db.rollback()


async def test_orphaned_team_embedding_choice_falls_through(db: AsyncSession) -> None:
    """An explicit team embedding choice whose connection was soft-deleted is skipped
    (like a soft-deleted model), so the chain falls through — here to no live default,
    yielding the clean ``NoEmbeddingModelConfigured`` rather than an ``EntityNotFound``."""
    org = await _seed_org(db)
    dead = _conn(org)
    db.add(dead)
    await db.flush()
    embed = _catalog(org, dead.id, model_type="embedding")
    db.add(embed)
    await db.flush()
    team = Team(org_id=org.id, name="KB", embedding_model_id=embed.id)
    db.add(team)
    await db.flush()

    dead.deleted_at = datetime.now(UTC)
    await db.flush()

    with pytest.raises(NoEmbeddingModelConfigured):
        await resolve_embedding_model_id(db, org_id=org.id, team_id=team.id, agent_id=None)
    await db.rollback()
