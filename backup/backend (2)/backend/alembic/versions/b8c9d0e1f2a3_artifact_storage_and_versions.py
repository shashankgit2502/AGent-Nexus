"""artifact storage + versions (ARTIFACTS.md §9)

Extends the existing ``artifacts`` table (TECHNICAL §11.4) with file-storage,
version, and message-linkage columns, and adds the ``artifact_versions`` history
table. **Extend, don't replace** (§9): our ``artifacts`` already carries
``kind``/``content``/``content_format`` from the init migration, so we add only the
new columns and skip the ``kind`` the spec ALTER lists (it is already present).

Ordering (TECHNICAL §11.8): alter ``artifacts`` (columns → FKs → check → index),
then create ``artifact_versions``, then its RLS policy. No ``updated_at`` trigger —
both rows are append-only / immutable-per-version (no ``updated_at`` column).

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1) artifacts: storage + version + linkage columns (§9) -------------------
    # All nullable or server-defaulted → backward compatible with existing rows
    # (no backfill needed; Postgres fills the defaults on existing rows).
    op.add_column("artifacts", sa.Column("conversation_message_id", sa.Uuid(), nullable=True))
    op.add_column("artifacts", sa.Column("producer_agent_id", sa.Uuid(), nullable=True))
    op.add_column("artifacts", sa.Column("filename", sa.Text(), nullable=True))
    op.add_column("artifacts", sa.Column("mime_type", sa.Text(), nullable=True))
    op.add_column("artifacts", sa.Column("storage_ref", sa.Text(), nullable=True))
    op.add_column("artifacts", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column(
        "artifacts",
        sa.Column("current_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "artifacts",
        sa.Column("status", sa.String(), server_default=sa.text("'ready'"), nullable=False),
    )
    op.add_column("artifacts", sa.Column("error", sa.Text(), nullable=True))

    # FKs: chat-message link CASCADE (artifact dies with its message); producer
    # agent SET NULL (an agent delete must not orphan-block its artifact, §9 note).
    op.create_foreign_key(
        "fk_artifacts_message",
        "artifacts",
        "messages",
        ["conversation_message_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_artifacts_producer_agent",
        "artifacts",
        "agents",
        ["producer_agent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_artifact_status",
        "artifacts",
        "status IN ('generating','ready','failed')",
    )
    op.create_index("ix_artifacts_message", "artifacts", ["conversation_message_id"], unique=False)

    # 2) artifact_versions: immutable per-version snapshots (Canvas history) -----
    op.create_table(
        "artifact_versions",
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("storage_ref", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_artifact_versions_org_id"), "artifact_versions", ["org_id"], unique=False
    )
    op.create_index("ix_av_artifact", "artifact_versions", ["artifact_id"], unique=False)
    op.create_index(
        "uq_artifact_version", "artifact_versions", ["artifact_id", "version"], unique=True
    )

    # 3) Row-Level Security (§11.7) — the org_isolation policy every tenant table
    # carries (artifacts already has it from the init migration; the new versions
    # table needs it too).
    op.execute("ALTER TABLE artifact_versions ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE artifact_versions FORCE ROW LEVEL SECURITY;")
    op.execute(
        "CREATE POLICY org_isolation ON artifact_versions "
        "USING (org_id = current_setting('app.current_org', true)::uuid);"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS org_isolation ON artifact_versions;")
    op.drop_index("uq_artifact_version", table_name="artifact_versions")
    op.drop_index("ix_av_artifact", table_name="artifact_versions")
    op.drop_index(op.f("ix_artifact_versions_org_id"), table_name="artifact_versions")
    op.drop_table("artifact_versions")

    op.drop_index("ix_artifacts_message", table_name="artifacts")
    op.drop_constraint("ck_artifact_status", "artifacts", type_="check")
    op.drop_constraint("fk_artifacts_producer_agent", "artifacts", type_="foreignkey")
    op.drop_constraint("fk_artifacts_message", "artifacts", type_="foreignkey")
    op.drop_column("artifacts", "error")
    op.drop_column("artifacts", "status")
    op.drop_column("artifacts", "current_version")
    op.drop_column("artifacts", "size_bytes")
    op.drop_column("artifacts", "storage_ref")
    op.drop_column("artifacts", "mime_type")
    op.drop_column("artifacts", "filename")
    op.drop_column("artifacts", "producer_agent_id")
    op.drop_column("artifacts", "conversation_message_id")
