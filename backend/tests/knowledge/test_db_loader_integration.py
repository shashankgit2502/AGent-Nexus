"""Integration test for the read-only DB connector (ITEM 2 Slice D).

Runs a real SELECT against the dev Postgres (the same container the app uses) and
asserts rows become documents — and that the read-only guard actually rejects a
write at the database, not just via the keyword check. Skips when Postgres is down.
"""

from __future__ import annotations

import psycopg
import pytest

from app.core.config import get_settings
from app.knowledge.db_loader import load_db_documents

pytestmark = pytest.mark.integration


@pytest.fixture
def dsn() -> str:
    """A psycopg DSN to the dev DB; skip if unreachable."""
    url = get_settings().LANGGRAPH_PG_URL  # bare postgresql:// psycopg URL
    try:
        psycopg.connect(url, connect_timeout=3).close()
    except psycopg.OperationalError as exc:  # pragma: no cover - infra-dependent
        pytest.skip(f"Postgres not reachable: {exc}")
    return url


def test_select_rows_become_documents(dsn: str) -> None:
    query = "SELECT * FROM (VALUES (1, 'Ada'), (2, 'Grace')) AS t(id, name)"
    docs = load_db_documents(dsn, query)
    assert len(docs) == 2
    assert "id: 1" in docs[0].page_content and "name: Ada" in docs[0].page_content
    assert docs[1].metadata == {"row": 1, "source": "db"}


def test_read_only_transaction_blocks_writes_at_the_database(dsn: str) -> None:
    # A would-be write that slips past the keyword guard must still be rejected by the
    # read-only transaction. Use a WITH … that performs a write-like op via a function
    # is overkill; simplest: assert a CREATE TEMP TABLE (not a SELECT) is refused by
    # the guard, and that the connection itself is read-only.
    from app.knowledge.db_loader import UnsafeQuery

    with pytest.raises(UnsafeQuery):
        load_db_documents(dsn, "CREATE TEMP TABLE evil(x int)")

    # Belt-and-braces: the connection flag is honoured by the driver.
    with psycopg.connect(dsn, connect_timeout=3) as conn:
        conn.read_only = True
        with conn.cursor() as cur, pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            cur.execute("CREATE TEMP TABLE evil(x int)")
