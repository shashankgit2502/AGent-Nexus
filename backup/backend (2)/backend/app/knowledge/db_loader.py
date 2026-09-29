"""Read-only database connector for ``kind='db'`` knowledge sources (Slice D).

Runs a user-supplied **SELECT** against a user-supplied **DSN** and turns each row
into a ``Document`` (``column: value`` lines, like the CSV/XLSX loaders, so columns
survive chunking). Per the locked scope (ARCH §10.5.1): *read-only*, Postgres via the
``psycopg`` we already depend on.

Safety (defence-in-depth, R5 — never trust external input):
  * the query must be a **single** statement starting with ``SELECT``/``WITH``;
  * the session runs with ``default_transaction_read_only = on`` **and** the psycopg
    connection's ``read_only`` flag — so any write is rejected at the DB even if the
    keyword check is bypassed;
  * a ``statement_timeout`` bounds runaway queries and a row cap bounds huge results;
  * a short ``connect_timeout`` bounds an unreachable host.

The DSN intentionally targets the user's own database (often internal), so — unlike
URL fetch — there is no public-host SSRF block here; that is the feature.
"""

from __future__ import annotations

import re

import psycopg
from langchain_core.documents import Document

# Bounds (tunable later per source). Conservative defaults for prose-RAG over rows.
_MAX_ROWS = 10_000
_STATEMENT_TIMEOUT_MS = 30_000
_CONNECT_TIMEOUT_S = 10

# A query we will run must *start* with SELECT or WITH (CTE → SELECT) and be a single
# statement. The read-only transaction is the authoritative guard; this is the cheap
# fail-fast on obvious misuse.
_SELECT_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


class UnsafeQuery(ValueError):
    """A db-connector query is not a single read-only SELECT."""


def _validate_select(query: str) -> str:
    """Return the trimmed query if it is a single SELECT/WITH; else raise UnsafeQuery."""
    q = query.strip().rstrip(";").strip()
    if not q:
        raise UnsafeQuery("empty query")
    if ";" in q:
        raise UnsafeQuery("only a single statement is allowed (no ';')")
    if not _SELECT_RE.match(q):
        raise UnsafeQuery("only SELECT (or WITH … SELECT) queries are allowed")
    return q


def _row_to_document(columns: list[str], row: tuple[object, ...], index: int) -> Document | None:
    pairs = [f"{col}: {val}" for col, val in zip(columns, row, strict=False) if val is not None]
    if not pairs:
        return None
    return Document(page_content="\n".join(pairs), metadata={"row": index, "source": "db"})


def load_db_documents(dsn: str, query: str) -> list[Document]:
    """Run a read-only SELECT over ``dsn`` and return one Document per non-empty row.

    Raises:
        UnsafeQuery: the query is not a single read-only SELECT.
        psycopg.Error: connection/query failure (surfaced to the worker as ``failed``).
    """
    safe_query = _validate_select(query)
    with psycopg.connect(dsn, connect_timeout=_CONNECT_TIMEOUT_S, autocommit=False) as conn:
        conn.read_only = True  # psycopg refuses writes on this connection
        with conn.cursor() as cur:
            cur.execute("SET default_transaction_read_only = on")
            cur.execute(f"SET statement_timeout = {_STATEMENT_TIMEOUT_MS}")
            cur.execute(safe_query)  # noqa: S608 — validated single read-only SELECT, read-only txn
            columns = [d.name for d in cur.description or []]
            rows = cur.fetchmany(_MAX_ROWS)
    docs = [d for i, r in enumerate(rows) if (d := _row_to_document(columns, r, i)) is not None]
    return docs
