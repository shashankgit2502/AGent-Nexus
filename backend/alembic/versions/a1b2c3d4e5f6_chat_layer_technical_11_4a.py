"""chat & conversational layer (TECHNICAL 11.4a)

Adds the Step-10 chat layer (ARCH §8.5): ``conversations`` / ``messages`` /
``attachments`` and the run-ownership XOR on ``runs`` (a run belongs to a Session
**or** a Conversation, never both).

Ordering (TECHNICAL §11.8): create ``conversations`` first so the ``runs``
self-extension and the child tables can reference it; then alter ``runs``; then the
child tables; then the ``updated_at`` trigger and RLS policies.

Revision ID: a1b2c3d4e5f6
Revises: 93f5133c2d9a
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "93f5133c2d9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# New tenant-scoped tables → RLS keyed on app.current_org (TECHNICAL §11.7),
# matching the policy the init migration installs on every tenant table.
_NEW_TENANT_TABLES = ("conversations", "messages", "attachments")


def upgrade() -> None:
    # 1) conversations -------------------------------------------------------
    op.create_table(
        "conversations",
        sa.Column("team_id", sa.Uuid(), nullable=True),
        sa.Column("model_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("is_playground", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conversations_org_id"), "conversations", ["org_id"], unique=False)
    op.create_index("uq_conv_thread", "conversations", ["thread_id"], unique=True)
    op.create_index(
        "ix_conv_org",
        "conversations",
        ["org_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND NOT is_playground"),
    )

    # 2) runs: run-ownership XOR (a run belongs to a Session OR a Conversation) ---
    op.alter_column("runs", "session_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column("runs", sa.Column("conversation_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_runs_conversation_id",
        "runs",
        "conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(op.f("ix_runs_conversation_id"), "runs", ["conversation_id"], unique=False)
    op.create_check_constraint(
        "runs_owner_chk",
        "runs",
        "(session_id IS NOT NULL) <> (conversation_id IS NOT NULL)",
    )

    # 3) messages ------------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column(
            "deep_collaborate", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant','system')", name="ck_message_role"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_org_id"), "messages", ["org_id"], unique=False)
    op.create_index("ix_messages_conv", "messages", ["conversation_id", "created_at"], unique=False)

    # 4) attachments ---------------------------------------------------------
    op.create_table(
        "attachments",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("uri", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), server_default=sa.text("'transient'"), nullable=False),
        sa.Column("promoted_source_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("scope IN ('transient','knowledge')", name="ck_attachment_scope"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["promoted_source_id"], ["knowledge_sources.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_attachments_org_id"), "attachments", ["org_id"], unique=False)
    op.create_index("ix_attach_conv", "attachments", ["conversation_id"], unique=False)

    # 5) updated_at trigger (only conversations carries updated_at) (§11.6) ---
    op.execute(
        "CREATE TRIGGER trg_conversations_updated BEFORE UPDATE ON conversations "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    # 6) Row-Level Security (§11.7) — same policy the init migration installs ---
    for table in _NEW_TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"CREATE POLICY org_isolation ON {table} "
            "USING (org_id = current_setting('app.current_org', true)::uuid);"
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_conversations_updated ON conversations;")

    op.drop_index("ix_attach_conv", table_name="attachments")
    op.drop_index(op.f("ix_attachments_org_id"), table_name="attachments")
    op.drop_table("attachments")

    op.drop_index("ix_messages_conv", table_name="messages")
    op.drop_index(op.f("ix_messages_org_id"), table_name="messages")
    op.drop_table("messages")

    # Revert the runs XOR extension. Rows owned by a conversation cannot satisfy
    # the restored NOT NULL on session_id, so this downgrade assumes no chat runs
    # exist (the standard "downgrade unwinds the feature" expectation).
    op.drop_constraint("runs_owner_chk", "runs", type_="check")
    op.drop_index(op.f("ix_runs_conversation_id"), table_name="runs")
    op.drop_constraint("fk_runs_conversation_id", "runs", type_="foreignkey")
    op.drop_column("runs", "conversation_id")
    op.alter_column("runs", "session_id", existing_type=sa.Uuid(), nullable=False)

    op.drop_index(
        "ix_conv_org",
        table_name="conversations",
        postgresql_where=sa.text("deleted_at IS NULL AND NOT is_playground"),
    )
    op.drop_index("uq_conv_thread", table_name="conversations")
    op.drop_index(op.f("ix_conversations_org_id"), table_name="conversations")
    op.drop_table("conversations")
