"""Unit tests for the RunEventEmitter choke point (ARCH §24.3)."""

from __future__ import annotations

import asyncio

from app.streaming.emitter import RunEventEmitter
from app.streaming.events import AGUIEvent
from app.streaming.publisher import InProcessEventPublisher
from app.streaming.store import InMemoryRunEventStore


async def test_emit_assigns_monotonic_seq_and_persists() -> None:
    store = InMemoryRunEventStore()
    emitter = RunEventEmitter(
        session_id="s", run_id="r", store=store, publisher=InProcessEventPublisher()
    )

    await emitter.emit({"type": "run_start", "data": {}})
    await emitter.emit({"type": "contribution", "data": {}})
    await emitter.emit({"type": "run_finished", "data": {}})

    persisted = await store.replay("r")
    assert [e["seq"] for e in persisted] == [1, 2, 3]
    assert [e["type"] for e in persisted] == ["run_start", "contribution", "run_finished"]
    assert emitter.last_seq == 3


async def test_emit_publishes_to_live_subscribers() -> None:
    store = InMemoryRunEventStore()
    publisher = InProcessEventPublisher()
    emitter = RunEventEmitter(session_id="s", run_id="r", store=store, publisher=publisher)

    received: list[AGUIEvent] = []

    async def consume() -> None:
        async for event in publisher.subscribe("r"):
            received.append(event)
            return

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    await emitter.emit({"type": "run_start", "data": {}})
    await asyncio.wait_for(task, timeout=1.0)

    assert received[0]["type"] == "run_start"
    assert received[0]["seq"] == 1


async def test_for_run_continues_seq_across_resume() -> None:
    """A resuming emitter must not restart seq at 1 (ARCH §24.3 monotonic per run)."""
    store = InMemoryRunEventStore()
    publisher = InProcessEventPublisher()

    first = await RunEventEmitter.for_run(
        session_id="s", run_id="r", store=store, publisher=publisher
    )
    await first.emit({"type": "run_start", "data": {}})
    await first.emit({"type": "hitl_request", "data": {}})

    resumed = await RunEventEmitter.for_run(
        session_id="s", run_id="r", store=store, publisher=publisher
    )
    await resumed.emit({"type": "hitl_resolved", "data": {}})

    assert [e["seq"] for e in await store.replay("r")] == [1, 2, 3]
