"""Wipe ALL data from the database — a one-command clean slate.

Truncates every row from every public table, leaving the schema and the
framework bookkeeping intact, so the DB is functionally brand-new. This is the
runnable-script twin of the ``c3d4e5f6a7b8_wipe_all_data`` Alembic migration —
same keep-list, same single atomic ``TRUNCATE … RESTART IDENTITY CASCADE`` — but
invokable any time without touching the migration chain.

Wipes:
  - every app table (teams, agents, sessions, runs, providers, knowledge, chat…)
  - LangGraph checkpointer data (``checkpoints`` / ``checkpoint_blobs`` /
    ``checkpoint_writes``) and store data (``store`` / ``store_vectors``)
  - PGVector ``langchain_*`` tables and any other public table

Deliberately KEPT (so migrations + frameworks still work afterwards):
  - ``alembic_version``        — the migration head pointer
  - ``checkpoint_migrations``  — LangGraph PostgresSaver setup bookkeeping
  - ``store_migrations``       — LangGraph PostgresStore setup bookkeeping

⚠️  DESTRUCTIVE & IRREVERSIBLE. Truncated rows cannot be restored. Defaults to a
DRY RUN that only lists the tables it *would* truncate (with row counts). Pass
``--yes`` to actually wipe.

Usage (from backend/, with the project venv):
    uv run python scripts/wipe_all_data.py          # dry run — shows what it'd do
    uv run python scripts/wipe_all_data.py --yes     # actually wipe everything
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: E402

from app.db.session import engine  # noqa: E402

engine.echo = False
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("wipe_all_data")

# Tables that must survive a "complete cleanup": the Alembic head pointer and the
# two LangGraph *_migrations tables that record framework setup. Truncating those
# would leave Alembic/LangGraph unable to recognise their own schema.
KEEP = ("alembic_version", "checkpoint_migrations", "store_migrations")

# Truncate every public base table except the keep-list, in ONE atomic statement.
# CASCADE follows FK dependencies (so order is irrelevant); RESTART IDENTITY resets
# any identity columns. Mirrors the wipe_all_data migration exactly.
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
    END IF;
END $$;
"""


async def _target_tables(conn: AsyncConnection) -> list[str]:
    """Public tables that would be truncated (everything except the keep-list)."""
    rows = (
        await conn.execute(
            text(
                """
                SELECT tablename FROM pg_tables
                 WHERE schemaname = 'public' AND tablename <> ALL(CAST(:keep AS text[]))
                 ORDER BY tablename
                """
            ),
            {"keep": list(KEEP)},
        )
    ).all()
    return [r[0] for r in rows]


async def _report(conn: AsyncConnection, tables: list[str]) -> int:
    """Print each target table's row count; return the grand total."""
    total = 0
    logger.info("Tables to TRUNCATE (%d):", len(tables))
    for t in tables:
        # Table name comes from pg_tables (trusted catalog), safe to interpolate.
        n = int(await conn.scalar(text(f'SELECT count(*) FROM "{t}"')) or 0)
        total += n
        logger.info("  %-30s %d rows", t, n)
    logger.info("Kept (untouched): %s", ", ".join(KEEP))
    return total


async def run(confirm: bool) -> int:
    async with engine.begin() as conn:
        tables = await _target_tables(conn)
        if not tables:
            logger.info("No tables to wipe.")
            return 0

        total = await _report(conn, tables)

        if not confirm:
            logger.info("\nDRY RUN — nothing wiped (%d rows would be deleted).", total)
            logger.info("Re-run with --yes to wipe everything.")
            return 0

        logger.warning("\nWIPING — truncating %d tables (%d rows)…", len(tables), total)
        await conn.execute(text(_WIPE_SQL))
        logger.warning("Done. The database is now empty (schema + framework bookkeeping kept).")
    return 0


async def _amain(confirm: bool) -> int:
    """Run + dispose the engine in ONE event loop (the pool is loop-bound)."""
    try:
        return await run(confirm)
    finally:
        await engine.dispose()


def main() -> None:
    p = argparse.ArgumentParser(description="Truncate ALL data from the database.")
    p.add_argument("--yes", action="store_true", help="actually wipe (default: dry run)")
    args = p.parse_args()
    sys.exit(asyncio.run(_amain(args.yes)))


if __name__ == "__main__":
    main()
