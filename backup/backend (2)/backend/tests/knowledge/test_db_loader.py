"""Unit tests for the read-only DB connector query guard (ITEM 2 Slice D).

The pure ``_validate_select`` guard (SELECT/WITH only, single statement) and the
row→Document mapping. Actually running a query needs a live Postgres and lives in
the integration test (``test_db_loader_integration``); here we cover the security
gate and shaping, offline.
"""

from __future__ import annotations

import pytest

from app.knowledge.db_loader import UnsafeQuery, _row_to_document, _validate_select


def test_validate_select_allows_select_and_cte() -> None:
    assert _validate_select("SELECT id, name FROM users") == "SELECT id, name FROM users"
    assert _validate_select("  with t as (select 1) select * from t  ").startswith("with")
    # trailing semicolon is trimmed, not rejected
    assert _validate_select("SELECT 1;") == "SELECT 1"


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE users SET name='x'",
        "DELETE FROM users",
        "DROP TABLE users",
        "INSERT INTO t VALUES (1)",
        "SELECT 1; DROP TABLE users",  # piggy-backed statement
        "   ",  # empty
    ],
)
def test_validate_select_rejects_non_select_and_multi_statement(query: str) -> None:
    with pytest.raises(UnsafeQuery):
        _validate_select(query)


def test_row_to_document_renders_columns_and_skips_nulls() -> None:
    doc = _row_to_document(["id", "name", "note"], (1, "Ada", None), 0)
    assert doc is not None
    assert "id: 1" in doc.page_content
    assert "name: Ada" in doc.page_content
    assert "note" not in doc.page_content  # None skipped
    assert doc.metadata == {"row": 0, "source": "db"}


def test_row_to_document_returns_none_for_all_null_row() -> None:
    assert _row_to_document(["a", "b"], (None, None), 3) is None
