"""Hard-delete teams (by name) and every trace they leave behind.

Removes the named teams *completely* — not the soft-delete (``deleted_at``) the
app uses, but a real ``DELETE`` plus a sweep of the framework-managed stores that
have **no** foreign key back to ``teams`` and therefore never cascade.

What a plain ``DELETE FROM teams`` already cascades (DB-level ON DELETE CASCADE):
    agents, skills, agent_skills, knowledge_sources, sessions, conversations,
    runs, artifacts, run_events, messages, attachments.

What this script must clean *manually* (framework tables, no FK to teams):
    1. ``store`` (LangGraph long-term memory; ``store_vectors`` cascades from it)
       — rows whose namespace ``prefix`` carries ``team.<team_id>`` (§25.1).
    2. ``checkpoints`` / ``checkpoint_blobs`` / ``checkpoint_writes`` (short-term
       state) — rows keyed by a ``thread_id`` owned by the teams' sessions or
       conversations.
    3. ``langchain_pg_embedding`` (PGVector RAG chunks) — rows whose ``cmetadata``
       tags ``team_id`` = a deleted team (§10.5.1).

⚠️  DESTRUCTIVE & IRREVERSIBLE. Defaults to a DRY RUN that only reports what it
*would* delete. Pass ``--commit`` to actually delete.

Usage (from backend/, with the project venv):
    uv run python scripts/delete_teams.py                 # dry run, default names
    uv run python scripts/delete_teams.py --commit        # actually delete
    uv run python scripts/delete_teams.py --commit "Chat Team" "KB team"
    uv run python scripts/delete_teams.py --org-id <uuid>  # scope to one org

Matching is case-insensitive (``lower(name)``) and includes already
soft-deleted teams, so a name that was only soft-deleted is still purged.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from uuid import UUID

# Allow `python scripts/delete_teams.py` from the backend/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import bindparam, text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: E402

from app.db.session import engine  # noqa: E402

# The app engine sets echo=True in local dev; turn it off so the report is readable.
engine.echo = False

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("delete_teams")

# The teams to purge by default (the entries asked for). Override on the CLI.
DEFAULT_NAMES: tuple[str, ...] = (
    "Chat Team",
    "KB team",
    "Profile",
    "Conv",
    "Team cc 756",
    "Acceptance Runs",
    "Iso",
    "Mem",
)


async def _table_exists(conn: AsyncConnection, table: str) -> bool:
    """True if a public table exists (framework tables may be absent locally)."""
    found = await conn.scalar(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"})
    return found is not None


async def _resolve_teams(
    conn: AsyncConnection, names: list[str], org_id: UUID | None, prefix: bool
) -> list[dict]:
    """Resolve team names → rows (id, org_id, name, deleted_at), case-insensitive.

    ``prefix=False`` → exact match on ``lower(name)``.
    ``prefix=True``  → match teams whose name *starts with* a given token, so a
    label like ``Chat Team`` purges the whole ``Chat Team <hex>`` family. The
    token is matched at a word boundary (token, or token followed by a space) to
    avoid ``KB`` also catching ``KB Team`` unless ``KB Team`` is itself listed —
    callers list the exact families they want.
    """
    if prefix:
        # Build one OR group per token: name = token OR name ILIKE 'token %'.
        clauses, params = [], {"org_id": org_id}
        for i, tok in enumerate(names):
            clauses.append(f"(lower(name) = :n{i} OR name ILIKE :p{i})")
            params[f"n{i}"] = tok.lower()
            params[f"p{i}"] = f"{tok} %"
        where = " OR ".join(clauses)
        stmt = text(
            f"""
            SELECT id, org_id, name, deleted_at
              FROM teams
             WHERE ({where})
               AND (CAST(:org_id AS uuid) IS NULL OR org_id = CAST(:org_id AS uuid))
             ORDER BY name
            """
        )
        rows = (await conn.execute(stmt, params)).mappings().all()
        return [dict(r) for r in rows]

    stmt = text(
        """
        SELECT id, org_id, name, deleted_at
          FROM teams
         WHERE lower(name) IN :names
           AND (CAST(:org_id AS uuid) IS NULL OR org_id = CAST(:org_id AS uuid))
         ORDER BY name
        """
    ).bindparams(bindparam("names", expanding=True))
    rows = (
        await conn.execute(stmt, {"names": [n.lower() for n in names], "org_id": org_id})
    ).mappings().all()
    return [dict(r) for r in rows]


async def _collect_thread_ids(conn: AsyncConnection, team_ids: list[UUID]) -> list[str]:
    """Gather every checkpointer thread_id owned by the teams (sessions + convos)."""
    stmt = text(
        """
        SELECT thread_id FROM sessions      WHERE team_id IN :ids
        UNION
        SELECT thread_id FROM conversations WHERE team_id IN :ids
        """
    ).bindparams(bindparam("ids", expanding=True))
    return [r[0] for r in (await conn.execute(stmt, {"ids": team_ids})).all()]


async def _count(conn: AsyncConnection, sql: str, params: dict) -> int:
    return int(await conn.scalar(text(sql).bindparams(*_expanding(params)), params) or 0)


def _expanding(params: dict) -> list:
    """bindparam(expanding=True) for any list-valued param so IN clauses work."""
    return [bindparam(k, expanding=True) for k, v in params.items() if isinstance(v, list)]


def _store_prefix_clause() -> str:
    """SQL predicate matching store namespaces under any of :team_ids.

    Namespace shape is ``org.<org>.team.<team>.…`` joined by '.', so a team's
    rows are those whose prefix contains the ``team.<id>`` segment (followed by
    end-of-string or another '.').
    """
    return (
        "EXISTS (SELECT 1 FROM unnest(CAST(:team_strs AS text[])) AS t(id) "
        "WHERE store.prefix LIKE '%team.' || t.id "
        "   OR store.prefix LIKE '%team.' || t.id || '.%')"
    )


async def _report(conn: AsyncConnection, team_ids: list[UUID], threads: list[str]) -> None:
    """Print how many dependent rows the purge will remove (dry-run preview)."""
    tstrs = [str(t) for t in team_ids]

    relational = {
        "agents": "SELECT count(*) FROM agents WHERE team_id IN :ids",
        "skills": "SELECT count(*) FROM skills WHERE team_id IN :ids",
        "knowledge_sources": "SELECT count(*) FROM knowledge_sources WHERE team_id IN :ids",
        "sessions": "SELECT count(*) FROM sessions WHERE team_id IN :ids",
        "conversations": "SELECT count(*) FROM conversations WHERE team_id IN :ids",
    }
    logger.info("  cascading relational rows:")
    for label, sql in relational.items():
        logger.info("    %-20s %d", label, await _count(conn, sql, {"ids": team_ids}))

    logger.info("  framework rows (manual sweep):")
    if await _table_exists(conn, "store"):
        n = await conn.scalar(
            text(f"SELECT count(*) FROM store WHERE {_store_prefix_clause()}"),
            {"team_strs": tstrs},
        )
        logger.info("    %-20s %d", "store (memory)", int(n or 0))
    if threads and await _table_exists(conn, "checkpoints"):
        n = await _count(
            conn, "SELECT count(*) FROM checkpoints WHERE thread_id IN :th", {"th": threads}
        )
        logger.info("    %-20s %d  (%d threads)", "checkpoints", n, len(threads))
    if await _table_exists(conn, "langchain_pg_embedding"):
        n = await _count(
            conn,
            "SELECT count(*) FROM langchain_pg_embedding WHERE cmetadata->>'team_id' IN :ids",
            {"ids": tstrs},
        )
        logger.info("    %-20s %d", "vector chunks", n)


async def _purge(conn: AsyncConnection, team_ids: list[UUID], threads: list[str]) -> None:
    """Delete the framework rows, then the teams (cascade does the rest)."""
    tstrs = [str(t) for t in team_ids]

    # 1. Short-term checkpoints, by thread_id (children first; no FK to teams).
    if threads:
        for tbl in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            if await _table_exists(conn, tbl):
                res = await conn.execute(
                    text(f"DELETE FROM {tbl} WHERE thread_id IN :th").bindparams(
                        bindparam("th", expanding=True)
                    ),
                    {"th": threads},
                )
                logger.info("  deleted %-22s %d", tbl, res.rowcount)

    # 2. Long-term memory; store_vectors cascades via its FK to store.
    if await _table_exists(conn, "store"):
        res = await conn.execute(
            text(f"DELETE FROM store WHERE {_store_prefix_clause()}"), {"team_strs": tstrs}
        )
        logger.info("  deleted %-22s %d", "store", res.rowcount)

    # 3. RAG vector chunks, by tenant metadata.
    if await _table_exists(conn, "langchain_pg_embedding"):
        res = await conn.execute(
            text(
                "DELETE FROM langchain_pg_embedding WHERE cmetadata->>'team_id' IN :ids"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": tstrs},
        )
        logger.info("  deleted %-22s %d", "langchain_pg_embedding", res.rowcount)

    # 4. The teams themselves — relational cascade removes everything FK-linked.
    res = await conn.execute(
        text("DELETE FROM teams WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        ),
        {"ids": team_ids},
    )
    logger.info("  deleted %-22s %d  (+ relational cascade)", "teams", res.rowcount)


async def run(
    names: list[str], org_id: UUID | None, commit: bool, prefix: bool
) -> int:
    async with engine.begin() as conn:
        teams = await _resolve_teams(conn, names, org_id, prefix)

        matched = [t["name"].lower() for t in teams]
        for tok in names:
            tl = tok.lower()
            hit = (tl + " ") if prefix else tl
            if not any(m == tl or (prefix and m.startswith(hit)) for m in matched):
                logger.warning("NO MATCH (skipped): %r", tok)

        if not teams:
            logger.info("No matching teams. Nothing to do.")
            return 0

        logger.info("Matched %d team(s):", len(teams))
        for t in teams:
            flag = "  [soft-deleted]" if t["deleted_at"] else ""
            logger.info("  - %-18s id=%s%s", t["name"], t["id"], flag)

        team_ids = [t["id"] for t in teams]
        threads = await _collect_thread_ids(conn, team_ids)

        await _report(conn, team_ids, threads)

        if not commit:
            logger.info("\nDRY RUN — nothing deleted. Re-run with --commit to apply.")
            # engine.begin() will commit this read-only tx; that's harmless.
            return 0

        logger.info("\nCOMMIT — deleting…")
        await _purge(conn, team_ids, threads)
        logger.info("Done. %d team(s) purged completely.", len(teams))
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Hard-delete teams by name and all their data.")
    p.add_argument("names", nargs="*", default=list(DEFAULT_NAMES), help="team names")
    p.add_argument("--commit", action="store_true", help="actually delete (default: dry run)")
    p.add_argument(
        "--prefix",
        action="store_true",
        help="treat each name as a family prefix ('Chat Team' → all 'Chat Team <hex>')",
    )
    p.add_argument("--org-id", type=UUID, default=None, help="restrict to one organization")
    args = p.parse_args(argv)
    if not args.names:  # empty list passed explicitly
        args.names = list(DEFAULT_NAMES)
    return args


async def _amain(args: argparse.Namespace) -> int:
    """Run + dispose the engine in ONE event loop (the pool is loop-bound)."""
    try:
        return await run(args.names, args.org_id, args.commit, args.prefix)
    finally:
        await engine.dispose()


def main() -> None:
    sys.exit(asyncio.run(_amain(_parse_args())))


if __name__ == "__main__":
    main()
