"""runtime embedding model on team + agent (ITEM 2, ARCH §9.5/§10.5)

Adds a runtime-selectable embedding model to ``teams`` and ``agents`` so knowledge
ingestion + retrieval resolve a real embedding model per source owner. Resolution
chain (app.knowledge embedding resolver): ``agents.embedding_model_id`` (private
override) → ``teams.embedding_model_id`` → org default embedding model.

Both columns are nullable FKs to ``model_catalog`` (a row whose ``model_type`` must
be ``'embedding'`` — enforced at the service layer, not the DB, since a CHECK can't
cross tables). The pgvector collection is keyed by the resolved model, so the
embedding dimension stays sticky per collection (§20 note 6).

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("embedding_model_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_teams_embedding_model",
        "teams",
        "model_catalog",
        ["embedding_model_id"],
        ["id"],
    )
    op.add_column("agents", sa.Column("embedding_model_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_agents_embedding_model",
        "agents",
        "model_catalog",
        ["embedding_model_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_agents_embedding_model", "agents", type_="foreignkey")
    op.drop_column("agents", "embedding_model_id")
    op.drop_constraint("fk_teams_embedding_model", "teams", type_="foreignkey")
    op.drop_column("teams", "embedding_model_id")
