"""Dashboard stats DTO (ARCH §14; FRONTEND_SPEC Dashboard).

A small read-only aggregate the Dashboard renders as headline tiles. All counts are
org-scoped (RLS + explicit ``org_id`` filter, TECHNICAL §11.7) and exclude
soft-deleted rows where the model is soft-deletable.
"""

from __future__ import annotations

from pydantic import BaseModel


class StatsRead(BaseModel):
    """Org-scoped headline counts for the Dashboard."""

    teams: int
    agents: int
    sessions: int
    runs: int
    completed_runs: int
    conversations: int
    knowledge_sources: int
