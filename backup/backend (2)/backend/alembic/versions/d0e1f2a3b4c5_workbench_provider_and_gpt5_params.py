"""Workbench provider + GPT-5 family request-schema controls

Two additive changes to the Model Resolution Layer, in one migration because
they touch the same three tables.

1. **Workbench provider.** Widens ``ck_conn_provider`` to admit ``'workbench'``
   (an APIM-fronted gateway proxying to an Azure-OpenAI-shaped endpoint) and adds
   ``llm_connections.config_metadata`` (JSONB) to carry its gateway settings —
   ``workbench_provider`` / ``charge_code`` / ``region_override`` /
   ``azureml_model_deployment``. JSONB rather than four discrete columns because
   gateway header sets are open-ended; adding one must not require a migration.
   It never holds a secret: the API key stays behind ``api_key_ref`` (ARCH §9.4).

2. **GPT-5 family.** Adds ``model_catalog.model_family`` — which *request schema*
   a model follows (``auto``/``gpt4``/``gpt5``), distinct from the existing
   ``supports_reasoning`` capability flag. Declaring it is the only way to
   classify an Azure deployment, whose name the customer chooses and which is
   what discovery writes into ``model_identifier``. Adds
   ``inference_profiles.verbosity`` (GPT-5 output-length control) and CHECK
   constraints pinning the widened ``reasoning_level`` vocabulary
   (``none``/``minimal``/``xhigh``/``max`` joined ``low``/``medium``/``high``).

Backward compatibility: every added column is nullable or defaulted, and every
CHECK admits NULL, so existing rows satisfy them untouched and resolve to
exactly the behaviour they have today (``model_family`` NULL == ``auto`` ==
detect from the name, which is what the code did before the column existed).

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROVIDERS_BEFORE = "'openai','anthropic','azure_openai','ollama','openrouter','openai_compatible'"
_PROVIDERS_AFTER = f"{_PROVIDERS_BEFORE},'workbench'"


def upgrade() -> None:
    # ── 1. Workbench provider ────────────────────────────────────────────────
    # A CHECK constraint cannot be altered in place; drop and recreate.
    op.drop_constraint("ck_conn_provider", "llm_connections", type_="check")
    op.create_check_constraint(
        "ck_conn_provider", "llm_connections", f"provider IN ({_PROVIDERS_AFTER})"
    )

    op.add_column(
        "llm_connections",
        sa.Column(
            "config_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # ── 2. GPT-5 family request-schema controls ──────────────────────────────
    op.add_column("model_catalog", sa.Column("model_family", sa.String(), nullable=True))
    op.create_check_constraint(
        "ck_catalog_model_family",
        "model_catalog",
        "model_family IS NULL OR model_family IN ('auto','gpt4','gpt5')",
    )

    op.add_column("inference_profiles", sa.Column("verbosity", sa.String(), nullable=True))
    op.create_check_constraint(
        "ck_profile_verbosity",
        "inference_profiles",
        "verbosity IS NULL OR verbosity IN ('low','medium','high')",
    )
    # ``reasoning_level`` was an unconstrained TEXT column, so it is pinned here
    # for the first time rather than widened. Any pre-existing value outside the
    # set would already have been rejected by the provider at request time.
    op.create_check_constraint(
        "ck_profile_reasoning_level",
        "inference_profiles",
        "reasoning_level IS NULL OR reasoning_level IN "
        "('none','minimal','low','medium','high','xhigh','max')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_profile_reasoning_level", "inference_profiles", type_="check")
    op.drop_constraint("ck_profile_verbosity", "inference_profiles", type_="check")
    op.drop_column("inference_profiles", "verbosity")

    op.drop_constraint("ck_catalog_model_family", "model_catalog", type_="check")
    op.drop_column("model_catalog", "model_family")

    op.drop_column("llm_connections", "config_metadata")

    # Narrowing the provider CHECK fails while any workbench row survives —
    # including soft-deleted ones, since the constraint does not read
    # ``deleted_at``. We refuse rather than delete them: ``model_catalog`` FKs to
    # ``llm_connections`` with ON DELETE CASCADE, so removing a connection here
    # would silently take its catalog models with it. Removing them is the
    # operator's decision, made through the API, not a side effect of a
    # downgrade.
    remaining = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM llm_connections WHERE provider = 'workbench'"))
        .scalar_one()
    )
    if remaining:
        raise RuntimeError(
            f"{remaining} workbench connection(s) still exist. Delete them (which "
            "cascades to their catalog models) before downgrading past "
            f"{revision}; this migration will not remove them for you."
        )

    op.drop_constraint("ck_conn_provider", "llm_connections", type_="check")
    op.create_check_constraint(
        "ck_conn_provider", "llm_connections", f"provider IN ({_PROVIDERS_BEFORE})"
    )
