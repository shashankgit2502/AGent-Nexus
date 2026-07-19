"""Chat & conversational layer (ARCH §8.5, TECHNICAL §11.4a).

The conversational surface that sits *above* the collaboration engine — it reuses
the same execution spine (the collab graph for team chat; one ``create_agent`` for
no-team chat), it is **not** a new engine (CLAUDE §3 locked decision).

* A :class:`Conversation` owns a checkpointer ``thread_id`` (multi-turn context,
  ARCH §8.5.2). ``team_id IS NULL`` ⇒ a no-team single-LLM chat; set ⇒ team chat.
  ``is_playground`` conversations are ephemeral and excluded from history.
* A :class:`Message` is one transcript turn. A *team-chat* assistant turn carries a
  ``run_id`` (run-per-turn, ARCH §8.5.2); a *no-team* turn has none (the message is
  produced without a run).
* An :class:`Attachment` is a chat file upload, **transient** to the conversation by
  default; "Save to team knowledge" promotes it into ``knowledge_sources`` and sets
  ``promoted_source_id`` (ARCH §8.5.3).

The run-ownership XOR (a run belongs to a Session **or** a Conversation) lives on
the ``runs`` table and is added here in :mod:`app.db.models.sessions` (§11.4a).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
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


class Conversation(UUIDPKMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A chat thread bound to a checkpointer ``thread_id`` (§11.4a).

    ``team_id`` NULL ⇒ no-team single-LLM chat (``model_ref`` holds the chosen
    connection/catalog/profile); set ⇒ team chat over the collab graph.
    """

    __tablename__ = "conversations"

    team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True
    )
    # {connection_id, model_id, profile_id} for no-team chat (ARCH §8.5.5).
    model_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    is_playground: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index("uq_conv_thread", "thread_id", unique=True),
        # Listing surface excludes playground + soft-deleted (ARCH §8.5.1).
        Index(
            "ix_conv_org",
            "org_id",
            postgresql_where=text("deleted_at IS NULL AND NOT is_playground"),
        ),
    )


class Message(UUIDPKMixin, OrgScopedMixin, Base):
    """One transcript turn. Derived → hard cascade, no soft-delete (§11.4a)."""

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set for team-chat assistant turns (run-per-turn); SET NULL if the run is
    # pruned. NULL for user turns and no-team assistant turns.
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    deep_collaborate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system')", name="ck_message_role"),
        Index("ix_messages_conv", "conversation_id", "created_at"),
    )


class Attachment(UUIDPKMixin, OrgScopedMixin, Base):
    """A chat file upload; transient by default (§11.4a, ARCH §8.5.3)."""

    __tablename__ = "attachments"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)  # file mime/type
    uri: Mapped[str] = mapped_column(String, nullable=False)  # object-storage location
    scope: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'transient'"))
    # The conversation-scoped knowledge_source this upload is ingested through (§8.5.3):
    # the file's chunks are embedded under it and retrieved by the per-turn attachment
    # tool. Lets the chat UI poll ingestion status. NULL until ingestion is registered.
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Set when "Save to team knowledge" promotes the file into knowledge_sources.
    promoted_source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("scope IN ('transient','knowledge')", name="ck_attachment_scope"),
        Index("ix_attach_conv", "conversation_id"),
    )
