"""Hard-delete stale inference profiles (by name prefix), safely.

Companion to ``delete_teams.py`` for the ``inference_profiles`` table — the
``Profile <hex>`` test rows the demo/acceptance flows leave behind. Unlike teams,
a profile has **no** framework data to sweep, but it *is* the target of
``agents.profile_id`` (a plain FK, no ``ON DELETE``), so deleting one that a
surviving agent still points at would raise a FK violation.

Policy (no silent mutation of surviving agents): only profiles with **zero**
referencing agents are deleted. Any still-referenced profile is reported and
skipped, so the operator can decide whether to repoint/delete those agents first.

⚠️  DESTRUCTIVE & IRREVERSIBLE. Dry run by default; pass ``--commit`` to delete.

Usage (from backend/, with the project venv):
    uv run python scripts/delete_profiles.py                  # dry run, 'Profile' prefix
    uv run python scripts/delete_profiles.py --commit
    uv run python scripts/delete_profiles.py --commit "Profile" "Embedding Model"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import bindparam, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: E402

from app.db.session import engine  # noqa: E402

engine.echo = False
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("delete_profiles")

DEFAULT_PREFIXES: tuple[str, ...] = ("Profile",)


async def _resolve(conn: AsyncConnection, prefixes: list[str]) -> list[dict]:
    """Profiles whose name == or starts with any prefix, + their agent ref count."""
    clauses, params = [], {}
    for i, tok in enumerate(prefixes):
        clauses.append(f"(lower(ip.name) = :n{i} OR ip.name ILIKE :p{i})")
        params[f"n{i}"] = tok.lower()
        params[f"p{i}"] = f"{tok} %"
    stmt = text(
        f"""
        SELECT ip.id, ip.name, ip.deleted_at,
               (SELECT count(*) FROM agents a WHERE a.profile_id = ip.id) AS refs
          FROM inference_profiles ip
         WHERE ({" OR ".join(clauses)})
         ORDER BY ip.name
        """
    )
    return [dict(r) for r in (await conn.execute(stmt, params)).mappings().all()]


async def run(prefixes: list[str], commit: bool) -> int:
    async with engine.begin() as conn:
        rows = await _resolve(conn, prefixes)
        if not rows:
            logger.info("No matching profiles. Nothing to do.")
            return 0

        deletable = [r["id"] for r in rows if r["refs"] == 0]
        blocked = [r for r in rows if r["refs"] > 0]

        logger.info("Matched %d profile(s): %d deletable, %d still referenced.",
                    len(rows), len(deletable), len(blocked))
        for r in blocked:
            logger.warning("  SKIP (referenced by %d agent[s]): %r", r["refs"], r["name"])

        if not deletable:
            logger.info("Nothing to delete (all matched profiles are still in use).")
            return 0

        if not commit:
            logger.info("\nDRY RUN — would delete %d profile(s). Re-run with --commit.",
                        len(deletable))
            return 0

        res = await conn.execute(
            text("DELETE FROM inference_profiles WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": deletable},
        )
        logger.info("\nCOMMIT — deleted %d profile(s).", res.rowcount)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Delete unreferenced inference profiles by name.")
    p.add_argument("prefixes", nargs="*", default=list(DEFAULT_PREFIXES))
    p.add_argument("--commit", action="store_true", help="actually delete (default: dry run)")
    args = p.parse_args()
    if not args.prefixes:
        args.prefixes = list(DEFAULT_PREFIXES)

    async def _amain() -> int:
        # Run + dispose the engine in ONE event loop (the pool is loop-bound).
        try:
            return await run(args.prefixes, args.commit)
        finally:
            await engine.dispose()

    sys.exit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
