"""Regression tests for the Alembic framework-table filter (R3, TECHNICAL §11.8).

Root cause being locked down: an earlier ``include_object`` excluded the prefix
``"store_"``, which matched ``store_migrations`` but **missed the bare ``store``
table** (LangGraph PostgresStore). Autogenerate then emitted ``DROP TABLE store``.
These tests fail if the filter ever stops excluding any framework table.
"""

from __future__ import annotations

import pytest

from app.db.alembic_filters import include_object, is_framework_table


@pytest.mark.parametrize(
    "name",
    [
        "store",  # ← the bare PostgresStore table (the regression)
        "store_migrations",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
        "langchain_pg_collection",
        "langchain_pg_embedding",
    ],
)
def test_framework_tables_are_excluded(name: str) -> None:
    assert is_framework_table(name) is True
    assert include_object(object(), name, "table", True, None) is False


@pytest.mark.parametrize(
    "name",
    ["teams", "agents", "sessions", "runs", "run_events", "organizations", "knowledge_sources"],
)
def test_app_tables_are_included(name: str) -> None:
    assert is_framework_table(name) is False
    assert include_object(object(), name, "table", False, None) is True


def test_non_table_objects_are_always_included() -> None:
    # Indexes/constraints on framework tables are handled with their table; the
    # filter only gates on type_ == "table".
    assert include_object(object(), "store", "index", True, None) is True
