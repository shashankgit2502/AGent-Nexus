"""Sessions, runs, artifacts, and the AG-UI event log (TECHNICAL §11.4).

A ``session`` owns a LangGraph checkpointer ``thread_id``. A ``run`` is one launched
query on that thread. ``run_events`` is the durable, replayable projection of the
AG-UI stream (ARCH §24.8) — the live blackboard itself lives in LangGraph state, not
a relational table (§11.4 note).

Step-10 (§11.4a): a ``run`` belongs to **either** a launched Session **or** a chat
Conversation — never both, never neither. ``session_id`` is therefore nullable, a
``conversation_id`` is added, and a ``CHECK`` enforces the XOR (ARCH §8.5.2).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import OrgScopedMixin, SoftDeleteMixin, TimestampMixin, UUIDPKMixin


class Session(UUIDPKMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A collaboration session bound to a checkpointer ``thread_id`` (§11.4)."""

    __tablename__ = "sessions"

    team_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'created'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (Index("uq_session_thread", "thread_id", unique=True),)


class Run(UUIDPKMixin, OrgScopedMixin, Base):
    """One launched query on a Session **or** Conversation thread (§11.4a).

    Derived → hard cascade, no soft-delete. Exactly one of ``session_id`` /
    ``conversation_id`` is set (the ``runs_owner_chk`` XOR, ARCH §8.5.2).
    """

    __tablename__ = "runs"

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    rounds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    converged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'running'"))
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "(session_id IS NOT NULL) <> (conversation_id IS NOT NULL)",
            name="runs_owner_chk",
        ),
    )


class Artifact(UUIDPKMixin, OrgScopedMixin, Base):
    """A run's persisted, downloadable output (ARTIFACTS.md §2/§9).

    Derived → hard cascade (§11.4). Anchored on ``run_id`` (the run already belongs
    to a session **or** a conversation via the XOR, so artifacts work in both with no
    new branching, §3). ``conversation_message_id`` additionally lets chat render an
    artifact inline on the assistant message (ChatGPT-style, §9).

    Storage (§7): **text** kinds may inline in ``content`` (small) or spill to object
    storage (``storage_ref`` set, ``content`` NULL); **binary** kinds always live in
    object storage. Each iterate creates a new :class:`ArtifactVersion`; ``current_version``
    advances while older versions stay downloadable (Canvas history). ``status`` carries
    the ``generating → ready|failed`` lifecycle for heavy async generation (§8).
    """

    __tablename__ = "artifacts"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Chat inline-rendering link (§9): set for chat-turn artifacts, NULL for session
    # artifacts. CASCADE: an artifact dies with the assistant message that produced it.
    conversation_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=True
    )
    # Which agent produced it (§9/§14); NULL when the Synthesizer emitted it. SET NULL
    # (not the spec's bare FK): a hard agent delete must not orphan-block an artifact
    # that outlives it (deviation flagged in the slice review).
    producer_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_format: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'markdown'")
    )
    storage_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    current_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'ready'"))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('generating','ready','failed')", name="ck_artifact_status"
        ),
        Index("ix_artifacts_message", "conversation_message_id"),
    )


class ArtifactVersion(UUIDPKMixin, OrgScopedMixin, Base):
    """One immutable snapshot of an artifact (ARTIFACTS.md §9, Canvas history).

    Each iterate persists a full snapshot here even though the wire carries JSON-Patch
    deltas (§11.2) — deltas are for live UX, snapshots are the durable downloadable
    record. ``content`` inlines text kinds; ``storage_ref`` points at object storage for
    binary kinds. ``UNIQUE(artifact_id, version)`` makes version addressing exact.
    """

    __tablename__ = "artifact_versions"

    artifact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("uq_artifact_version", "artifact_id", "version", unique=True),)


class RunEvent(UUIDPKMixin, OrgScopedMixin, Base):
    """Append-only AG-UI event log powering reconnect/replay (ARCH §24.8, §11.4).

    ``seq`` is monotonic per run; ``UNIQUE(run_id, seq)`` makes replay ordering and
    idempotent re-delivery exact (ARCH §24.3/§24.8).
    """

    __tablename__ = "run_events"

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("uq_run_event_seq", "run_id", "seq", unique=True),)
