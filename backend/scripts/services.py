"""Start / stop / check the backing services **without Docker** — manual startup.

The Docker-free replacement for ``docker compose up -d`` / ``down``. It does not
invoke Docker at all, so it is safe to keep alongside the existing compose setup:
on a machine that has Docker you keep using ``make up``; on one that doesn't, use
this.

    python scripts/services.py status     # what's reachable right now
    python scripts/services.py start      # start what's needed, wait until ready
    python scripts/services.py stop       # stop what this script can stop

What it manages
---------------
**PostgreSQL** — required. Three modes, chosen automatically:

  * *remote* — the host isn't local, so nothing can be started here. Readiness is
    checked and reported; starting/stopping is the remote's business.
  * *cluster* — ``PGDATA`` (and ``pg_ctl``) are available, so the cluster is started
    and stopped directly. This covers a portable/ZIP PostgreSQL that runs out of a
    user-writable folder with no Windows service and no admin rights.
  * *service* — PostgreSQL is installed as an OS service (the usual Windows
    installer outcome). We report readiness and name the service command rather
    than silently requiring elevation, because ``net start`` needs admin and a
    script that fails halfway is worse than one that tells you the command.

**Redis** — OPTIONAL, and skipped by default. Redis is used *only* for
cross-replica AG-UI fan-out (``RedisEventPublisher``), and only when
``STREAM_FANOUT=redis``. The default is ``memory`` — an in-process asyncio fan-out
that needs no Redis at all (ARCH §24.5: "Single-replica dev needs no Redis"). So a
single-developer machine can ignore Redis entirely; this script says so explicitly
instead of leaving you wondering whether something is missing.

Configuration (all optional — every value has a working default)
----------------------------------------------------------------
    LANGGRAPH_PG_URL   where Postgres is        (default: the app's own default)
    PGBIN              folder holding pg_ctl    (default: found on PATH)
    PGDATA             cluster data directory   (enables 'cluster' mode)
    PGCTL_LOG          pg_ctl logfile           (default: <PGDATA>/../pg_ctl.log)
    STREAM_FANOUT      memory | redis           (default: memory → Redis skipped)
    REDIS_URL          where Redis is           (default: redis://localhost:6379/0)

Exit codes: 0 = everything required is ready, 1 = something required is not.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Windows consoles default to a legacy code page (cp1252) that cannot encode the
# checkmarks/dashes below. Force UTF-8 on the streams logging writes to, replacing
# anything exotic rather than failing a startup check over a glyph.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("services")

# Matches app/core/config.py so running with no env set behaves like the app does.
DEFAULT_PG_URL = "postgresql://nex:nex@localhost:5433/nexagi"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"

# How long to wait for a service to accept connections after being started. A cold
# PostgreSQL start (WAL replay after an unclean shutdown) is comfortably slower than
# a warm one, so this is generous rather than snappy.
READY_TIMEOUT_S = 30.0
POLL_INTERVAL_S = 0.5

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", ""})


def _split(url: str, default_port: int) -> tuple[str, int]:
    """``(host, port)`` from a URL, tolerating a missing port."""
    parts = urlsplit(url)
    return (parts.hostname or "localhost"), (parts.port or default_port)


def _is_local(host: str) -> bool:
    return host.lower() in _LOCAL_HOSTS


def _port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """Whether a TCP connect succeeds — the cheapest liveness signal.

    Deliberately only the transport check; ``_pg_ready`` follows up with a real
    protocol handshake, because an open port can also mean "something else is
    listening there", which is a genuinely different problem to report.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ── PostgreSQL ────────────────────────────────────────────────────────────────


def _pg_ready(url: str) -> tuple[bool, str]:
    """Whether Postgres accepts a real connection. Returns ``(ok, detail)``.

    A protocol-level check, not just a port probe: a reachable port with wrong
    credentials or a missing database is *not* ready, and the distinction is what
    makes the message actionable.
    """
    try:
        import psycopg
    except ImportError:  # pragma: no cover — psycopg is a project dependency
        host, port = _split(url, 5432)
        return _port_open(host, port), "port open (psycopg unavailable for a full check)"

    try:
        with psycopg.connect(url, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_setting('server_version')")
            row = cur.fetchone()
        if row:
            return True, f"database {row[0]!r}, server {row[1]}"
        return True, "connected"
    except Exception as exc:  # noqa: BLE001 — any failure means "not ready", with the reason
        return False, f"{type(exc).__name__}: {str(exc).strip().splitlines()[0]}"


def _pg_ctl() -> str | None:
    """Path to ``pg_ctl``, from ``PGBIN`` or the PATH."""
    pgbin = os.environ.get("PGBIN", "").strip()
    if pgbin:
        candidate = Path(pgbin) / ("pg_ctl.exe" if os.name == "nt" else "pg_ctl")
        if candidate.exists():
            return str(candidate)
    return shutil.which("pg_ctl")


def _pg_mode(url: str) -> str:
    """``remote`` | ``cluster`` | ``service`` — how Postgres can be managed here."""
    host, _ = _split(url, 5432)
    if not _is_local(host):
        return "remote"
    if os.environ.get("PGDATA") and _pg_ctl():
        return "cluster"
    return "service"


def _pg_ctl_log() -> Path:
    """Where ``pg_ctl`` writes. Outside PGDATA so a wipe doesn't take the log."""
    configured = os.environ.get("PGCTL_LOG", "").strip()
    if configured:
        return Path(configured)
    pgdata = Path(os.environ["PGDATA"])
    return pgdata.parent / "pg_ctl.log"


def _wait_ready(url: str, label: str) -> bool:
    """Poll until the service answers, or the timeout expires."""
    deadline = time.monotonic() + READY_TIMEOUT_S
    last = ""
    while time.monotonic() < deadline:
        ok, detail = _pg_ready(url)
        if ok:
            logger.info("  %s ready — %s", label, detail)
            return True
        last = detail
        time.sleep(POLL_INTERVAL_S)
    logger.error("  %s did NOT become ready in %.0fs — %s", label, READY_TIMEOUT_S, last)
    return False


def pg_status(url: str) -> bool:
    mode = _pg_mode(url)
    host, port = _split(url, 5432)
    ok, detail = _pg_ready(url)
    logger.info("PostgreSQL [%s]  %s:%s", mode, host, port)
    if ok:
        logger.info("  ready — %s", detail)
        return True
    if _port_open(host, port):
        logger.error("  port is open but the handshake failed — %s", detail)
        logger.error("  (wrong credentials, or the 'nexagi' database does not exist yet)")
        logger.error("  fix: uv run python scripts/db_bootstrap.py --check-only")
    else:
        logger.error("  not reachable — %s", detail)
    return False


def pg_start(url: str) -> bool:
    mode = _pg_mode(url)
    host, port = _split(url, 5432)

    if _pg_ready(url)[0]:
        logger.info("PostgreSQL already running on %s:%s", host, port)
        return True

    if mode == "remote":
        logger.error("PostgreSQL at %s is remote — cannot be started from here.", host)
        return _wait_ready(url, "PostgreSQL")

    if mode == "service":
        logger.error("PostgreSQL is not running on %s:%s and PGDATA is not set.", host, port)
        logger.error(
            "  It is likely installed as an OS service. Start it with (needs admin):\n"
            "    Windows:  net start postgresql-x64-<major>\n"
            "    Linux:    sudo systemctl start postgresql\n"
            "    macOS:    brew services start postgresql\n"
            "  Or, for a portable/ZIP install this script CAN manage, set PGDATA and "
            "PGBIN and re-run."
        )
        return False

    # cluster mode — we own the lifecycle.
    pg_ctl = _pg_ctl()
    assert pg_ctl is not None  # guaranteed by _pg_mode
    pgdata = os.environ["PGDATA"]
    if not (Path(pgdata) / "PG_VERSION").exists():
        logger.error(
            "PGDATA=%s is not an initialised cluster (no PG_VERSION).\n"
            "  Initialise it once with:  initdb -D %s -U postgres --encoding=UTF8",
            pgdata,
            pgdata,
        )
        return False

    log_path = _pg_ctl_log()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Starting PostgreSQL cluster at %s (port %s)…", pgdata, port)
    result = subprocess.run(  # noqa: S603 — fixed executable, no shell
        [pg_ctl, "-D", pgdata, "-l", str(log_path), "-o", f"-p {port}", "start"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.error("  pg_ctl start failed (%s): %s", result.returncode, result.stderr.strip())
        logger.error("  see the log: %s", log_path)
        return False
    return _wait_ready(url, "PostgreSQL")


def pg_stop(url: str) -> bool:
    mode = _pg_mode(url)
    if mode != "cluster":
        logger.info("PostgreSQL [%s] — not managed by this script; leaving it alone.", mode)
        return True
    pg_ctl = _pg_ctl()
    assert pg_ctl is not None
    pgdata = os.environ["PGDATA"]
    logger.info("Stopping PostgreSQL cluster at %s…", pgdata)
    # ``fast`` rolls back in-flight transactions and shuts down promptly, rather than
    # waiting for clients to disconnect on their own (``smart``, the default).
    result = subprocess.run(  # noqa: S603 — fixed executable, no shell
        [pg_ctl, "-D", pgdata, "-m", "fast", "stop"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.error("  pg_ctl stop failed: %s", result.stderr.strip())
        return False
    logger.info("  stopped")
    return True


# ── Redis (optional) ──────────────────────────────────────────────────────────


def _redis_required() -> bool:
    """Redis matters only for the cross-replica fan-out backend (ARCH §24.5)."""
    return os.environ.get("STREAM_FANOUT", "memory").strip().lower() == "redis"


def _redis_ready(url: str) -> tuple[bool, str]:
    """A real PING when the client is installed, else a port probe."""
    try:
        import redis  # noqa: PLC0415 — optional dependency, imported only when used
    except ImportError:
        host, port = _split(url, 6379)
        return _port_open(host, port), "port open (redis client not installed)"
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=3)
        client.ping()
        return True, "PONG"
    except Exception as exc:  # noqa: BLE001 — any failure means "not ready", with the reason
        return False, f"{type(exc).__name__}: {str(exc).strip().splitlines()[0]}"


def redis_status(url: str) -> bool:
    if not _redis_required():
        logger.info("Redis  skipped — not required (STREAM_FANOUT=memory)")
        logger.info("  the in-process fan-out serves a single replica; set")
        logger.info("  STREAM_FANOUT=redis only for multi-worker deployments")
        return True
    host, port = _split(url, 6379)
    ok, detail = _redis_ready(url)
    logger.info("Redis  %s:%s", host, port)
    if ok:
        logger.info("  ready — %s", detail)
    else:
        logger.error("  not reachable — %s", detail)
    return ok


def redis_start(url: str) -> bool:
    if not _redis_required():
        logger.info("Redis  skipped — not required (STREAM_FANOUT=memory)")
        return True
    if _redis_ready(url)[0]:
        logger.info("Redis already running")
        return True

    host, _ = _split(url, 6379)
    if not _is_local(host):
        logger.error("Redis at %s is remote — cannot be started from here.", host)
        return False

    # Memurai is the maintained Redis-compatible server for Windows; native Redis
    # does not ship for Windows. Either is fine — the client speaks the same protocol.
    binary = shutil.which("redis-server") or shutil.which("memurai")
    if binary is None:
        logger.error(
            "STREAM_FANOUT=redis but no redis-server/memurai binary was found.\n"
            "  Either install one, or set STREAM_FANOUT=memory (single replica needs "
            "no Redis)."
        )
        return False

    logger.info("Starting %s…", binary)
    subprocess.Popen(  # noqa: S603 — resolved executable, no shell
        [binary],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if _redis_ready(url)[0]:
            logger.info("  Redis ready")
            return True
        time.sleep(POLL_INTERVAL_S)
    logger.error("  Redis did not become ready in %.0fs", READY_TIMEOUT_S)
    return False


# ── Entry point ───────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start/stop/check Postgres and Redis without Docker.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("action", choices=("start", "stop", "status"))
    args = parser.parse_args(argv)

    pg_url = os.environ.get("LANGGRAPH_PG_URL", DEFAULT_PG_URL)
    redis_url = os.environ.get("REDIS_URL", DEFAULT_REDIS_URL)

    if args.action == "status":
        pg_ok = pg_status(pg_url)
        logger.info("")
        redis_ok = redis_status(redis_url)
    elif args.action == "start":
        pg_ok = pg_start(pg_url)
        logger.info("")
        redis_ok = redis_start(redis_url)
    else:
        pg_ok = pg_stop(pg_url)
        redis_ok = True

    ok = pg_ok and redis_ok
    if args.action in ("start", "status"):
        logger.info("")
        if ok:
            logger.info("✓ All required services ready.")
            logger.info("  next: uv run uvicorn app.main:app --reload")
        else:
            logger.error("✗ Something required is not ready (see above).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
