"""Session / run DTOs (ARCH §14, §8, §21.4; TECHNICAL §11.4)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class SessionCreate(BaseModel):
    """Payload for ``POST /teams/{id}/sessions``.

    ``thread_id`` is optional — the server generates a unique one when omitted
    (it is the LangGraph checkpointer thread, ARCH §10).
    """

    thread_id: str | None = None


class SessionRead(ORMModel):
    """Session as returned to clients."""

    id: UUID
    org_id: UUID
    team_id: UUID
    thread_id: str
    status: str
    created_at: datetime


class RunLaunch(BaseModel):
    """Payload for ``POST /sessions/{id}/run`` (ARCH §8/§21.4).

    ``deep_collaborate`` selects the full multi-round graph (HITL on) vs the
    lightweight 1-round/no-HITL path (ARCH §8.5) — the same graph, parameterized.
    """

    query: str = Field(min_length=1)
    max_rounds: int = Field(default=3, ge=1, le=10)
    # τ back to the locked ARCH §8 value. It had been raised to 0.95 to compensate for
    # agents scoring themselves; scores are now peer-adjusted (§8.1), so the compensation
    # is obsolete and would only make convergence unreachable.
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    deep_collaborate: bool = True


class RunRead(ORMModel):
    """Run as returned to clients (the launch response carries the AG-UI stream id).

    Exactly one of ``session_id`` / ``conversation_id`` is set — a run belongs to a
    launched Session or a chat Conversation (ARCH §8.5.2 / §11.4a XOR).
    """

    id: UUID
    org_id: UUID
    session_id: UUID | None
    conversation_id: UUID | None
    query: str
    rounds: int
    converged: bool
    status: str
    started_at: datetime | None
    finished_at: datetime | None


class RunLaunchResponse(BaseModel):
    """The launch result: how to subscribe + whether it paused at HITL."""

    run: RunRead
    interrupted: bool  # paused at the human gate, awaiting POST /sessions/{id}/resume
    stream_url: str  # WS /sessions/{id}/stream?run_id=...


class ResumeRequest(BaseModel):
    """Payload for ``POST /sessions/{id}/resume`` — the human's HITL decision."""

    run_id: UUID
    decision: Literal["approve", "edit", "reject"]
    content: str | None = None  # edited final output (edit only)
    reason: str | None = None  # rejection reason (reject only)


class ArtifactRead(ORMModel):
    """A run's persisted output as returned to clients (ARCH §14, §11.4).

    ``kind`` is ``synthesis`` for an approved/edited run or ``rejected`` when the
    human rejected the converged candidate; ``content`` is the markdown body
    (``None`` only for a rejection with no recorded reason).
    """

    id: UUID
    run_id: UUID
    kind: str
    content: str | None
    content_format: str
    created_at: datetime
