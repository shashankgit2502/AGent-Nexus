"""Knowledge sources + observability tables (TECHNICAL §11.5).

``knowledge_sources`` is the relational registry of ingested RAG sources (the chunk
vectors themselves live in PGVector-managed tables, §11.5 note). ``usage_events`` and
``audit_log`` are the production metering + governance trails.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
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


class KnowledgeSource(UUIDPKMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A registered RAG source.

    Scope: ``conversation_id`` set = a **transient chat attachment** (ARCH §8.5.3,
    conversation-private, ``team_id`` may be NULL for no-team chats); otherwise a team
    KB source where ``agent_id`` NULL = team-shared, set = agent-private (§10.5).
    """

    __tablename__ = "knowledge_sources"

    # Nullable since a no-team conversation attachment has no owning team (§8.5.3);
    # team KB sources always set it.
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True
    )
    # Set for a transient chat attachment ingested into a conversation-scoped namespace
    # (ARCH §8.5.3); NULL for ordinary team-KB sources.
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)  # file|url|db|team_doc
    uri: Mapped[str | None] = mapped_column(String, nullable=True)
    # Typed config for connector kinds (Slice D). For kind='db': {dsn, query} —
    # a read-only DSN + a SELECT. JSONB so future connectors extend it freely.
    connector_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("kind IN ('file','url','db','team_doc')", name="ck_ks_kind"),
        CheckConstraint("status IN ('pending','ingesting','ready','failed')", name="ck_ks_status"),
    )


class UsageEvent(UUIDPKMixin, OrgScopedMixin, Base):
    """Per-call token/cost metering for dashboard KPIs (§11.5)."""

    __tablename__ = "usage_events"

    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    model_identifier: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    ts: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_usage_org_ts", "org_id", "ts"),)


class AuditLog(UUIDPKMixin, OrgScopedMixin, Base):
    """Who-did-what governance trail (§11.5)."""

    __tablename__ = "audit_log"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, nullable=False)  # 'connection.create' etc.
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ts: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_audit_org_ts", "org_id", "ts"),)
