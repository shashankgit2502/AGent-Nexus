"""Default inference profile — the org's whole-run reasoning model (ARCH §4.1/§4.6).

Adds ``inference_profiles.is_default``: the profile whose model runs the Orchestrator's
**planner** and the **synthesizer** — the two reasoning steps that belong to no single
agent. Before this, that model was whichever agent the roster query happened to return
first, which was both arbitrary and non-deterministic (no ``ORDER BY``).

Why a column and not a setting: the model layer is tenant **data** (Connection →
Catalog → Profile are org-scoped rows chosen in Settings → AI), so a BYO-LLM
deployment must be able to pick this per org, from the UI. This mirrors the existing
model-selection-as-data precedent in ``app/knowledge/embedding_selection.py``.

Mutual exclusion is enforced in the database by a **partial unique index** over
``org_id`` restricted to live default rows, so two defaults cannot coexist even if a
concurrent request races the API's clear-then-set.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "uq_inference_profiles_one_default_per_org"


def upgrade() -> None:
    op.add_column(
        "inference_profiles",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # One live default per org. Partial (WHERE) so the many non-default rows are
    # unconstrained, and soft-deleted profiles never block a new default.
    op.create_index(
        _INDEX,
        "inference_profiles",
        ["org_id"],
        unique=True,
        postgresql_where=sa.text("is_default AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="inference_profiles")
    op.drop_column("inference_profiles", "is_default")
