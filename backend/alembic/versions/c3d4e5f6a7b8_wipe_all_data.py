"""wipe all data — complete clean slate (maintenance migration)

Truncates **every** row from the database, leaving the schema and the framework
bookkeeping intact, so the DB is functionally brand-new. Wipes:
  - all 20 app tables (teams, agents, sessions, runs, providers, knowledge, chat…)
  - the LangGraph checkpointer **data** (``checkpoints`` / ``checkpoint_blobs`` /
    ``checkpoint_writes``) and store **data** (``store``)
  - any other public table (e.g. PGVector ``langchain_*``) that may exist

Deliberately KEPT (so migrations + frameworks still work afterwards):
  - ``alembic_version``        — the migration head pointer
  - ``checkpoint_migrations``  — LangGraph PostgresSaver setup bookkeeping
  - ``store_migrations``       — LangGraph PostgresStore setup bookkeeping

⚠️  DESTRUCTIVE & IRREVERSIBLE. Truncated rows cannot be restored, so ``downgrade``
is a no-op. To make this safe to sit in the upgrade chain, the wipe is **opt-in**:
a plain ``alembic upgrade head`` is a NO-OP unless the operator explicitly sets
``ALEMBIC_ALLOW_DATA_WIPE=1`` for that invocation. This prevents an accidental
production wipe while still giving local/dev a one-command clean slate:

    # bash / git-bash
    ALEMBIC_ALLOW_DATA_WIPE=1 uv run alembic upgrade head

    # PowerShell
    $env:ALEMBIC_ALLOW_DATA_WIPE = "1"; uv run alembic upgrade head

To wipe again later (this migration is already applied), re-stamp and re-run:

    uv run alembic downgrade a1b2c3d4e5f6
    ALEMBIC_ALLOW_DATA_WIPE=1 uv run alembic upgrade head

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-06-20
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

# Truthy spellings that arm the wipe.
_TRUTHY = {"1", "true", "yes", "on"}

# Tables that must survive a "complete cleanup": the Alembic head pointer and the
# two LangGraph *_migrations tables that record framework setup. Truncating those
# would leave Alembic/LangGraph unable to recognise their own schema.
_KEEP = ("alembic_version", "checkpoint_migrations", "store_migrations")

# Truncate every public base table except the keep-list, in ONE atomic statement.
# CASCADE follows FK dependencies (so order is irrelevant); RESTART IDENTITY resets
# any identity columns. UUID PKs / app-managed seq columns are unaffected — harmless.
_WIPE_SQL = """
DO $$
DECLARE
    keep    text[] := ARRAY['alembic_version', 'checkpoint_migrations', 'store_migrations'];
    targets text;
BEGIN
    SELECT string_agg(format('%I.%I', schemaname, tablename), ', ')
      INTO targets
      FROM pg_tables
     WHERE schemaname = 'public'
       AND tablename <> ALL(keep);

    IF targets IS NULL THEN
        RAISE NOTICE 'wipe_all_data: no tables to truncate';
    ELSE
        EXECUTE 'TRUNCATE TABLE ' || targets || ' RESTART IDENTITY CASCADE';
        RAISE NOTICE 'wipe_all_data: truncated %', targets;
    END IF;
END $$;
"""


def _wipe_armed() -> bool:
    return os.getenv("ALEMBIC_ALLOW_DATA_WIPE", "").strip().lower() in _TRUTHY


def upgrade() -> None:
    """Truncate all data — but only when explicitly armed (see module docstring)."""
    if not _wipe_armed():
        logger.warning(
            "wipe_all_data: SKIPPED (no data touched). This destructive migration is "
            "opt-in — set ALEMBIC_ALLOW_DATA_WIPE=1 and re-run to truncate every table."
        )
        return

    logger.warning("wipe_all_data: ARMED — truncating ALL tables except %s", ", ".join(_KEEP))
    op.execute(_WIPE_SQL)
    logger.warning("wipe_all_data: complete — the database is now empty.")


def downgrade() -> None:
    """No-op: truncated rows cannot be restored (this migration only deletes data)."""
    logger.warning("wipe_all_data: downgrade is a no-op (deleted data cannot be recovered).")
