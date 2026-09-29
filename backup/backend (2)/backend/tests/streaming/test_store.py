"""Unit tests for the in-memory run-event log + replay (ARCH §24.8)."""

from __future__ import annotations

from app.streaming.events import build_event
from app.streaming.store import InMemoryRunEventStore


def _event(run_id: str, seq: int) -> dict:
    return build_event({"type": "contribution"}, session_id="s", run_id=run_id, seq=seq)


async def test_append_then_replay_returns_all_in_order() -> None:
    store = InMemoryRunEventStore()
    for seq in (1, 2, 3):
        await store.append(_event("r", seq))

    replayed = await store.replay("r")
    assert [e["seq"] for e in replayed] == [1, 2, 3]


async def test_replay_after_seq_returns_only_missed_events() -> None:
    """ARCH §24.8: a reconnecting client gets only events after the seq it saw."""
    store = InMemoryRunEventStore()
    for seq in (1, 2, 3, 4):
        await store.append(_event("r", seq))

    assert [e["seq"] for e in await store.replay("r", after_seq=2)] == [3, 4]


async def test_replay_isolated_per_run() -> None:
    store = InMemoryRunEventStore()
    await store.append(_event("r1", 1))
    await store.append(_event("r2", 1))

    assert len(await store.replay("r1")) == 1
    assert await store.replay("unknown") == []


async def test_last_seq_tracks_highest_persisted() -> None:
    store = InMemoryRunEventStore()
    assert await store.last_seq("r") == 0  # nothing yet
    await store.append(_event("r", 1))
    await store.append(_event("r", 2))
    assert await store.last_seq("r") == 2
