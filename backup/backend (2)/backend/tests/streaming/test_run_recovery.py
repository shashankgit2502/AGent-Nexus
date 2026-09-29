"""Regression: orphaned runs left ``running`` by a restart are finalized (ARCH §24.8).

Root cause (R3): a run executes on a background asyncio task; if the process stops
mid-run (restart/crash/reload) the task dies, the ``runs`` row stays ``running``
forever, and no terminal AG-UI event is ever emitted — so a reconnecting client's
stream replays the partial log and hangs on "thinking" indefinitely. The fix
(``recover_orphaned_runs``) finalizes such runs on startup and emits a terminal
run-scoped ``error`` event so the stream terminates.

Live-DB integration (the project's stated testing preference): seeds a real org +
team + session + ``running`` Run against Postgres, then drives the recovery with a
real in-memory event store/publisher and asserts the run is finalized and a
terminal error event was emitted. Requires the migrated DB (``alembic upgrade
head``); marked ``integration``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.core.identity import seed_default_organization
from app.db.models import Run, Session, Team
from app.db.session import AsyncSessionLocal, engine
from app.streaming.publisher import InProcessEventPublisher
from app.streaming.run_recovery import recover_orphaned_runs
from app.streaming.store import InMemoryRunEventStore

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test() -> AsyncGenerator[None, None]:
    """Release pooled asyncpg connections on the test's own loop.

    pytest-asyncio gives each test a fresh event loop; the module-global engine
    pools connections bound to the first loop, so a connection GC'd after a later
    loop closes raises "Event loop is closed". Disposing the pool inside each
    test's loop (the same cleanup app shutdown does) avoids that cross-loop teardown.
    """
    yield
    await engine.dispose()


async def _seed_running_run() -> str:
    """Create a real org→team→session→``running`` Run; return the run id (str)."""
    async with AsyncSessionLocal() as db:
        org_id = await seed_default_organization(db)
        team = Team(org_id=org_id, name=f"Recovery Team {uuid4().hex[:8]}")
        db.add(team)
        await db.flush()
        session = Session(org_id=org_id, team_id=team.id, thread_id=f"thr-{uuid4().hex}")
        db.add(session)
        await db.flush()
        run = Run(
            org_id=org_id,
            session_id=session.id,
            query="stuck forever?",
            status="running",
            started_at=datetime.now(UTC),
        )
        db.add(run)
        await db.commit()
        return str(run.id)


async def test_orphaned_run_is_finalized_and_emits_terminal_error() -> None:
    run_id = await _seed_running_run()

    store = InMemoryRunEventStore()
    app = SimpleNamespace(
        state=SimpleNamespace(event_store=store, event_publisher=InProcessEventPublisher())
    )

    count = await recover_orphaned_runs(app)  # type: ignore[arg-type]
    assert count >= 1  # at least our seeded orphan

    # The run row is finalized — no longer "running", with a finish timestamp.
    async with AsyncSessionLocal() as db:
        recovered = await db.get(Run, UUID(run_id))
        assert recovered is not None
        assert recovered.status == "failed"
        assert recovered.finished_at is not None

    # A terminal run-scoped error event was emitted so a reconnecting client's
    # replay ends instead of hanging on "thinking".
    events = await store.replay(run_id)
    assert events, "expected a terminal event for the orphaned run"
    terminal = events[-1]
    assert terminal["type"] == "error"
    assert terminal["data"]["scope"] == "run"


async def test_paused_run_is_left_alone() -> None:
    """A ``paused`` run is suspended at the HITL gate, not orphaned — never touched."""
    async with AsyncSessionLocal() as db:
        org_id = await seed_default_organization(db)
        team = Team(org_id=org_id, name=f"Paused Team {uuid4().hex[:8]}")
        db.add(team)
        await db.flush()
        session = Session(org_id=org_id, team_id=team.id, thread_id=f"thr-{uuid4().hex}")
        db.add(session)
        await db.flush()
        run = Run(org_id=org_id, session_id=session.id, query="awaiting human", status="paused")
        db.add(run)
        await db.commit()
        paused_id = run.id

    store = InMemoryRunEventStore()
    app = SimpleNamespace(
        state=SimpleNamespace(event_store=store, event_publisher=InProcessEventPublisher())
    )
    await recover_orphaned_runs(app)  # type: ignore[arg-type]

    async with AsyncSessionLocal() as db:
        still = await db.get(Run, paused_id)
        assert still is not None
        assert still.status == "paused"  # untouched
    assert await store.replay(str(paused_id)) == []  # no terminal event emitted
