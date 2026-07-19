"""conversation-scoped attachment ingestion (Bug 2, ARCH §8.5.3)

Wires transient chat uploads into the existing knowledge pipeline as
**conversation-scoped** sources:

* ``knowledge_sources.conversation_id`` — nullable FK to ``conversations``; set for a
  transient chat attachment ingested into a conversation-private vector namespace.
* ``knowledge_sources.team_id`` becomes **nullable** — a no-team conversation's
  attachment has no owning team (resolution falls to the org-default embedding model).
* ``attachments.source_id`` — nullable FK to ``knowledge_sources`` linking a chat
  upload to the source it is ingested through (lets the chat UI poll ingest status).

Retrieval scopes these chunks by ``org_id`` + ``conversation_id`` (a separate
namespace from team/agent knowledge, which never sees them — §8.5.3).

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # knowledge_sources.team_id → nullable (no-team conversation attachments).
    op.alter_column("knowledge_sources", "team_id", existing_type=sa.Uuid(), nullable=True)

    # knowledge_sources.conversation_id — transient chat-attachment scope.
    op.add_column(
        "knowledge_sources", sa.Column("conversation_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_ks_conversation",
        "knowledge_sources",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_ks_conversation", "knowledge_sources", ["conversation_id"]
    )

    # attachments.source_id — link a chat upload to its ingestion source.
    op.add_column("attachments", sa.Column("source_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_attach_source",
        "attachments",
        "knowledge_sources",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_attach_source", "attachments", type_="foreignkey")
    op.drop_column("attachments", "source_id")

    op.drop_index("ix_ks_conversation", table_name="knowledge_sources")
    op.drop_constraint("fk_ks_conversation", "knowledge_sources", type_="foreignkey")
    op.drop_column("knowledge_sources", "conversation_id")

    # Restore NOT NULL (any conversation-scoped rows must be cleared first).
    op.alter_column("knowledge_sources", "team_id", existing_type=sa.Uuid(), nullable=False)
