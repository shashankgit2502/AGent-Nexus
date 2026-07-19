"""Dashboard stats router (ARCH §14; FRONTEND_SPEC Dashboard).

A single read-only aggregate of org-scoped headline counts. Thin (R5): the counting
is a handful of ``COUNT(*)`` queries, each filtered by ``org_id`` (defence-in-depth
alongside the RLS GUC, §11.7) and — where the model is soft-deletable — restricted
to live rows so the tiles match what the list endpoints return.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DbSession, Org
from app.db.base import Base
from app.db.models import Agent, Conversation, KnowledgeSource, Run, Team
from app.db.models import Session as SessionModel
from app.schemas.stats import StatsRead

router = APIRouter(tags=["stats"])


async def _count(db: AsyncSession, model: type[Base], org_id: UUID, **filters: Any) -> int:
    """Count live, org-scoped rows of ``model`` (optional equality filters)."""
    cols: Any = model
    stmt = select(func.count()).select_from(model).where(cols.org_id == org_id)
    if hasattr(model, "deleted_at"):
        stmt = stmt.where(cols.deleted_at.is_(None))
    for name, value in filters.items():
        stmt = stmt.where(getattr(cols, name) == value)
    return int(await db.scalar(stmt) or 0)


@router.get("/stats", response_model=StatsRead)
async def get_stats(db: DbSession, org: Org) -> StatsRead:
    """Return org-scoped headline counts for the Dashboard (ARCH §14)."""
    return StatsRead(
        teams=await _count(db, Team, org.org_id),
        agents=await _count(db, Agent, org.org_id),
        sessions=await _count(db, SessionModel, org.org_id),
        runs=await _count(db, Run, org.org_id),
        completed_runs=await _count(db, Run, org.org_id, status="completed"),
        conversations=await _count(db, Conversation, org.org_id),
        knowledge_sources=await _count(db, KnowledgeSource, org.org_id),
    )
