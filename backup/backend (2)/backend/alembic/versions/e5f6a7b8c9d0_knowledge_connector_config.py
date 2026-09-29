"""knowledge_sources.connector_config for the DB connector (ITEM 2 Slice D)

Adds a nullable ``connector_config`` JSONB column to ``knowledge_sources``. For
``kind='db'`` sources it holds ``{"dsn": ..., "query": ...}`` (a read-only DSN + a
SELECT). JSONB (not two columns) keeps the connector extensible — future source
kinds can stash their own typed config without further migrations.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_sources",
        sa.Column("connector_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_sources", "connector_config")
