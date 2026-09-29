"""Org-recovery tests for ``PostgresRunEventStore._org_for`` (ARCH §24.8).

Regression: a client reconnecting to replay a run launched *before* a backend
restart hit ``RunOrgUnknown`` because the run→org map is in-process and the
restart wiped it. The org is durable on the ``runs`` row, so a cache miss must
recover it from the DB rather than fail. These tests fake the async session
factory so they need no live Postgres (the SQL itself is exercised in
integration / manual runs).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.streaming.store_pg import PostgresRunEventStore, RunOrgUnknown


class _FakeSession:
    """Async-context-manager stand-in whose ``scalar`` returns a scripted org."""

    def __init__(self, org: Any, *, on_query: list[int] | None = None) -> None:
        self._org = org
        self._on_query = on_query

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def scalar(self, *_args: object, **_kw: object) -> Any:
        if self._on_query is not None:
            self._on_query.append(1)
        return self._org


def _store_with_db(org: Any, *, query_log: list[int] | None = None) -> PostgresRunEventStore:
    def factory() -> _FakeSession:
        return _FakeSession(org, on_query=query_log)

    return PostgresRunEventStore(factory)  # type: ignore[arg-type]


async def test_org_recovered_from_db_on_cache_miss() -> None:
    """Cache miss (e.g. post-restart) → org is read from the durable runs row."""
    org = uuid4()
    store = _store_with_db(org)
    run_id = str(uuid4())
    assert await store._org_for(run_id) == org


async def test_recovered_org_is_cached_no_second_db_hit() -> None:
    """The recovered org is cached, so subsequent calls don't re-query the DB."""
    org = uuid4()
    query_log: list[int] = []
    store = _store_with_db(org, query_log=query_log)
    run_id = str(uuid4())
    await store._org_for(run_id)  # first call → 1 DB hit
    await store._org_for(run_id)  # second call → cache hit, no DB
    assert len(query_log) == 1


async def test_registered_run_never_touches_db() -> None:
    """The hot path (registered at launch) resolves from cache without any query."""
    org = uuid4()

    def exploding_factory() -> _FakeSession:
        raise AssertionError("registered run must not query the DB for its org")

    store = PostgresRunEventStore(exploding_factory)  # type: ignore[arg-type]
    run_id = str(uuid4())
    store.register_run(run_id, org)
    assert await store._org_for(run_id) == org


async def test_unknown_run_with_no_db_record_raises() -> None:
    """A run absent from both cache and DB is genuinely unknown → raise (not empty)."""
    store = _store_with_db(None)
    with pytest.raises(RunOrgUnknown, match="none on record"):
        await store._org_for(str(uuid4()))
