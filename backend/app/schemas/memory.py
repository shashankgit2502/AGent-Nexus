"""Memory Explorer API schemas (ARCH §14, FRONTEND_SPEC §14).

Request/response DTOs for the per-item memory CRUD surface (list/search/delete/pin).
The domain object is :class:`~app.memory.items.MemoryItem`; these are the boundary
shapes the router speaks (R5 — Pydantic v2 at the edges). ``seq`` (the internal
ordering key) is intentionally not exposed.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.memory.items import MemoryKind


class MemoryItemRead(BaseModel):
    """One long-term memory record as the Explorer sees it (§14)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: MemoryKind
    content: str
    pinned: bool
    created_at: datetime
    run_id: UUID | None = None


class MemoryPage(BaseModel):
    """A page of an agent's memory records (§14 pagination: {items,total,limit,offset})."""

    items: list[MemoryItemRead]
    total: int
    limit: int
    offset: int


class MemoryPinUpdate(BaseModel):
    """Pin/unpin a memory record (PATCH body)."""

    pinned: bool
