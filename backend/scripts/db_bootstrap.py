"""Provision the NEX AGI database on a machine with **no Docker** — one command.

This is the Docker-free twin of ``docker compose up -d`` + ``alembic upgrade head``.
Point it at an **already-installed** PostgreSQL server and it brings the database
to exactly the state the app expects, idempotently (safe to re-run):

  1. **Preflight** — connect, report the real server version, and check that the
     ``vector`` extension is *available* to this server.
  2. **Role + database** — create role ``nex`` and database ``nexagi`` if absent.
  3. **Extension** — ``CREATE EXTENSION IF NOT EXISTS vector`` in the target DB.
  4. **App tables** — run Alembic to ``head`` (10 migrations → 28 tables). Schema
     only: the two data-touching migrations are **opt-in** and skip by default, so a
     fresh database comes up empty rather than pre-populated. Set
     ``ALEMBIC_SEED_DEMO_DATA=1`` to insert the demo teams/agents, and
     ``ALEMBIC_ALLOW_DATA_WIPE=1`` to let the maintenance wipe migration truncate.
     You configure providers/models in the UI (Settings → AI), not here.
  5. **Framework tables** — create the LangGraph checkpointer/store schemas
     (``checkpoints*``, ``store*``).

Why step 5 exists (the trap this script closes)
-----------------------------------------------
Alembic does **not** own every table. The LangGraph ``PostgresSaver`` (checkpointer)
and ``PostgresStore`` (long-term memory) create their own schema at *app startup*,
and ``alembic/env.py`` deliberately excludes them from autogenerate. So a
migration-only bootstrap leaves a database that passes every migration and still
can't run a session. This script creates them up front so a fresh machine fails
here — loudly, with a readable error — rather than on the first request.

Why pgvector is checked FIRST
-----------------------------
The very first migration runs ``CREATE EXTENSION IF NOT EXISTS vector``, so a server
without pgvector dies on migration #1 with an opaque error. A plain PostgreSQL
install does **not** bundle pgvector (the ``pgvector/pgvector`` Docker image did —
that convenience is what you lose by dropping Docker). We therefore check
``pg_available_extensions`` before touching anything and, when it's missing, say
exactly which files go where instead of letting Alembic fail.

Nothing here touches the Docker setup. ``docker-compose.yml`` and the ``Makefile``
are unchanged; this script simply targets whatever URL it is given, so it works
just as well against the Docker Postgres on port 5433.

Usage (from backend/, with the project venv):
    # Diagnose only — changes nothing. RUN THIS FIRST on a new machine.
    uv run python scripts/db_bootstrap.py --check-only

    # Full provision against a local server on the default port 5432
    uv run python scripts/db_bootstrap.py --admin-url postgresql://postgres:PASS@localhost:5432/postgres

    # Provision, but the role/database already exist
    uv run python scripts/db_bootstrap.py --no-create-db

Notes:
  * ``--admin-url`` needs a **superuser** (usually ``postgres``) and is used only for
    steps 1–3. It is never stored and never logged with its password.
  * ``--url`` is the *application* URL (sync form). It defaults to
    ``LANGGRAPH_PG_URL``; the async ``DATABASE_URL`` used by Alembic is derived from
    it so the two can never disagree.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Windows consoles default to a legacy code page (cp1252), which cannot encode the
# arrows/checkmarks below — they arrive as '?' or raise. Force UTF-8 on the streams
# logging actually writes to. ``errors="replace"`` keeps a exotic terminal readable
# instead of crashing a provisioning run over a glyph.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("db_bootstrap")
# Alembic announces every autogenerate plugin at INFO the moment a Config is built,
# which buries the handful of lines an operator actually needs. Silenced by exact
# logger name (verified against alembic 1.18.4) rather than muting ``alembic``
# wholesale — "Running upgrade X -> Y" is the most useful output this script has.
logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)

# The app's expected identity. These match app/core/config.py defaults and the
# docker-compose service, so a Docker-provisioned DB and a natively-provisioned one
# are indistinguishable to the application.
APP_ROLE = "nex"
APP_PASSWORD = "nex"  # noqa: S105 — local dev credential, same as docker-compose
APP_DB = "nexagi"

# Minimum server major version. pgvector needs 13+, and the schema uses
# gen_random_uuid() (built in from 13) and JSONB features throughout.
MIN_PG_MAJOR = 13

_PGVECTOR_MISSING_HELP = """
pgvector is NOT available to this PostgreSQL server.

The first migration runs `CREATE EXTENSION IF NOT EXISTS vector`, so provisioning
cannot continue. A standard PostgreSQL install does not include pgvector; it has to
be added to the server's own directories (no rebuild, just a file copy):

  <postgres>/lib/vector.dll                     (Windows)  or  vector.so  (Linux/macOS)
  <postgres>/share/extension/vector.control
  <postgres>/share/extension/vector--*.sql

The build MUST match this server's major version ({major}) and architecture (x64),
or the server refuses to load it. Prebuilt Windows binaries:
  https://github.com/andreiramani/pgvector_pgsql_windows

Alternatives that need no local install:
  * a managed Postgres with pgvector preinstalled (Neon, Supabase) — pass its URL
    via --admin-url/--url;
  * a bundle that ships PG + pgvector together (e.g. vectorize-io/pg0).

Re-run `--check-only` after adding the files; no restart is usually needed, but
restart the server if the check still fails.
"""


def _redacted(conninfo: str) -> str:
    """A connection string safe to log — password removed, never guessed at."""
    parts = conninfo_to_dict(conninfo)
    parts.pop("password", None)
    return make_conninfo("", **parts)


def _to_sync_url(url: str) -> str:
    """Normalise a SQLAlchemy-style URL into something psycopg accepts.

    ``postgresql+asyncpg://`` / ``postgresql+psycopg://`` are SQLAlchemy dialect
    URLs; psycopg wants a plain ``postgresql://``. Accepting both means the caller
    can paste whichever URL they already have without it silently failing.
    """
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def _to_async_url(url: str) -> str:
    """The asyncpg URL Alembic/SQLAlchemy expect, derived from the sync one."""
    sync = _to_sync_url(url)
    if sync.startswith("postgresql://"):
        return "postgresql+asyncpg://" + sync[len("postgresql://") :]
    return sync


def _default_admin_url(app_url: str) -> str:
    """An admin URL guessed from the app URL: same host/port, ``postgres`` db.

    Only a convenience for the common local case. The user still supplies the
    superuser password (via the URL or PGPASSWORD); we never invent a credential.
    """
    parts = conninfo_to_dict(_to_sync_url(app_url))
    parts["dbname"] = "postgres"
    parts["user"] = os.environ.get("PGUSER", "postgres")
    if "PGPASSWORD" in os.environ:
        parts["password"] = os.environ["PGPASSWORD"]
    else:
        parts.pop("password", None)
    return make_conninfo("", **parts)


# ── Steps ─────────────────────────────────────────────────────────────────────


def preflight(admin_url: str) -> tuple[int, bool]:
    """Report the server version and whether pgvector is available.

    Returns ``(major_version, pgvector_available)``. Raises on an unreachable
    server or an unsupported version — both are hard stops, not warnings.
    """
    logger.info("→ Connecting to %s", _redacted(admin_url))
    with psycopg.connect(admin_url, connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute("SHOW server_version")
        row = cur.fetchone()
        version_text = str(row[0]) if row else "unknown"

        cur.execute("SELECT current_setting('server_version_num')::int")
        row = cur.fetchone()
        version_num = int(row[0]) if row else 0
        major = version_num // 10000

        logger.info("  server_version: %s  (major %d)", version_text, major)
        if major < MIN_PG_MAJOR:
            raise SystemExit(
                f"PostgreSQL {major} is too old; NEX AGI needs {MIN_PG_MAJOR}+ "
                "(gen_random_uuid, JSONB, pgvector)."
            )

        cur.execute("SELECT default_version FROM pg_available_extensions WHERE name = 'vector'")
        available = cur.fetchone()
        if available:
            logger.info("  pgvector available: yes (version %s)", available[0])
            return major, True

        logger.error("  pgvector available: NO")
        return major, False


def app_identity(app_url: str) -> tuple[str, str, str]:
    """``(role, password, dbname)`` taken from the application URL.

    Derived from the URL rather than from the module constants so the script always
    provisions *the database it is about to migrate*. Hardcoding them meant a custom
    ``--url`` created ``nex``/``nexagi`` and then ran migrations against a database
    that had never been created — a confusing failure two steps later.
    """
    parts = conninfo_to_dict(_to_sync_url(app_url))
    return (
        str(parts.get("user") or APP_ROLE),
        str(parts.get("password") or APP_PASSWORD),
        str(parts.get("dbname") or APP_DB),
    )


def ensure_role_and_database(admin_url: str, role: str, password: str, dbname: str) -> None:
    """Create the app role and database if they do not exist (idempotent).

    ``CREATE DATABASE`` cannot run inside a transaction block, hence autocommit.
    Identifiers are composed with ``psycopg.sql`` rather than f-strings: these values
    now come from a user-supplied URL, so quoting them correctly is a requirement,
    not a style preference (R5 — validate/escape at the boundary).
    """
    with psycopg.connect(admin_url, connect_timeout=10, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if cur.fetchone():
                logger.info("→ Role %r already exists", role)
            else:
                cur.execute(
                    sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(password)
                    )
                )
                logger.info("→ Created role %r", role)

            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone():
                logger.info("→ Database %r already exists", dbname)
            else:
                cur.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(dbname), sql.Identifier(role)
                    )
                )
                logger.info("→ Created database %r owned by %r", dbname, role)


def ensure_extension(admin_url: str, role: str, dbname: str) -> None:
    """Enable pgvector **in the target database**, as superuser.

    Done with the admin connection on purpose: ``CREATE EXTENSION`` requires
    superuser (or explicit grants), so leaving it to the app role would fail on a
    locked-down server. Running it here means the app role never needs elevation.
    """
    parts = conninfo_to_dict(admin_url)
    parts["dbname"] = dbname
    target = make_conninfo("", **parts)
    with psycopg.connect(target, connect_timeout=10, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = cur.fetchone()
            logger.info("→ pgvector enabled in %r (version %s)", dbname, row[0] if row else "?")
            # The app role must own the schema it writes to. A no-op when it already
            # owns the database; required when the DB pre-existed under another owner.
            cur.execute(sql.SQL("GRANT ALL ON SCHEMA public TO {}").format(sql.Identifier(role)))


def run_migrations() -> None:
    """Run Alembic to ``head`` in-process.

    In-process rather than shelling out to ``alembic``: one interpreter, one venv,
    and a real traceback instead of a captured exit code. ``env.py`` reads
    ``settings.DATABASE_URL``, which ``main()`` has already put in the environment.
    """
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    # Absolute, so the script works from any working directory.
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    logger.info("→ Running migrations to head…")
    command.upgrade(cfg, "head")


def report_revision(app_url: str) -> None:
    """Log the applied revision against the expected head.

    The applied revision is read straight from ``alembic_version`` rather than through
    ``MigrationContext``, which expects a SQLAlchemy connection — this path already
    holds a psycopg one, and borrowing an API with the wrong connection type is how a
    reporting helper turns into a crash on some future Alembic release.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()

    with psycopg.connect(_to_sync_url(app_url), connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.alembic_version') IS NOT NULL")
        row = cur.fetchone()
        if not (row and row[0]):
            logger.info("  alembic revision: none yet (alembic_version table absent)")
            return
        cur.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()
        current = row[0] if row else None

    state = "up to date" if current == head else "BEHIND"
    logger.info("  alembic revision: %s (head %s) — %s", current, head, state)


def setup_langgraph_tables(app_url: str) -> None:
    """Create the LangGraph checkpointer + store schemas.

    Uses the **sync** ``PostgresSaver``/``PostgresStore``. The app uses the ``.aio``
    variants at runtime, but both create the identical schema, and the sync classes
    sidestep the Windows event-loop policy issue that ``app/main.py`` documents — a
    provisioning script has no reason to inherit that constraint.
    """
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.store.postgres import PostgresStore

    url = _to_sync_url(app_url)
    logger.info("→ Creating LangGraph checkpointer tables…")
    with PostgresSaver.from_conn_string(url) as saver:
        saver.setup()
    logger.info("→ Creating LangGraph store tables (pgvector-indexed)…")
    with PostgresStore.from_conn_string(url) as store:
        store.setup()


def report_tables(app_url: str) -> None:
    """Log how many public tables exist, as a final sanity signal."""
    with psycopg.connect(_to_sync_url(app_url), connect_timeout=10) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        row = cur.fetchone()
        logger.info("  public tables: %s", row[0] if row else "?")


# ── Entry point ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision the NEX AGI database without Docker (idempotent).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url",
        default=None,
        help=(
            "Application DB URL (sync form, e.g. postgresql://nex:nex@localhost:5432/nexagi). "
            "Defaults to LANGGRAPH_PG_URL, else the app default (port 5433)."
        ),
    )
    parser.add_argument(
        "--admin-url",
        default=os.environ.get("ADMIN_DATABASE_URL"),
        help=(
            "Superuser URL to a maintenance DB, e.g. "
            "postgresql://postgres:PASS@localhost:5432/postgres. "
            "Defaults to ADMIN_DATABASE_URL, else guessed from --url."
        ),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Diagnose (version + pgvector + revision) and change nothing.",
    )
    parser.add_argument(
        "--no-create-db",
        action="store_true",
        help="Skip role/database creation (they already exist).",
    )
    parser.add_argument(
        "--skip-langgraph",
        action="store_true",
        help="Skip creating the LangGraph checkpointer/store tables.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Resolve the app URL, then publish BOTH forms into the environment *before* any
    # app module is imported — app.core.config caches its Settings on first read, so
    # importing it earlier would freeze the wrong URL and the script would migrate a
    # different database than the one it just provisioned.
    app_url = _to_sync_url(
        args.url
        or os.environ.get("LANGGRAPH_PG_URL")
        or f"postgresql://{APP_ROLE}:{APP_PASSWORD}@localhost:5433/{APP_DB}"
    )
    os.environ["LANGGRAPH_PG_URL"] = app_url
    os.environ["DATABASE_URL"] = _to_async_url(app_url)

    admin_url = args.admin_url or _default_admin_url(app_url)

    logger.info("NEX AGI database bootstrap")
    logger.info("  app URL:   %s", _redacted(app_url))
    logger.info("  admin URL: %s", _redacted(admin_url))
    logger.info("")

    try:
        major, has_vector = preflight(admin_url)
    except psycopg.OperationalError as exc:
        logger.error("\nCannot reach PostgreSQL: %s", exc)
        logger.error(
            "Check the server is running and the host/port/credentials are right.\n"
            "Tip: a local install usually listens on 5432, but the app defaults to "
            "5433 (the docker-compose mapping) — pass --url explicitly."
        )
        return 2

    if not has_vector:
        logger.error(_PGVECTOR_MISSING_HELP.format(major=major))
        return 3

    if args.check_only:
        logger.info("\n→ --check-only: no changes made.")
        try:
            report_revision(app_url)
            report_tables(app_url)
        except psycopg.OperationalError:
            logger.info(
                "  (app database not reachable yet — run without --check-only to create it)"
            )
        return 0

    role, password, dbname = app_identity(app_url)
    if not args.no_create_db:
        ensure_role_and_database(admin_url, role, password, dbname)
    ensure_extension(admin_url, role, dbname)
    run_migrations()
    if not args.skip_langgraph:
        setup_langgraph_tables(app_url)

    logger.info("\n✓ Provisioned. Final state:")
    report_revision(app_url)
    report_tables(app_url)
    logger.info(
        "\nNext: set these for the app (see backend/.env.example)\n"
        "  DATABASE_URL=%s\n  LANGGRAPH_PG_URL=%s\n"
        "then start it with:  uv run uvicorn app.main:app --reload",
        _to_async_url(app_url),
        app_url,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
