"""Tests for the AG-UI WebSocket endpoint — reconnect replay (ARCH §24.2/§24.8).

Covers the reconnect/replay contract through a real FastAPI app and the Starlette
test WebSocket client: a (re)connecting client passing ``after_seq`` receives exactly
the events it missed, in order. (Live cross-thread fan-out over the test client is
covered structurally by ``test_publisher`` + ``test_emitter``/``test_runner``;
here we lock the replay handshake that makes reconnect correct.)
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.streaming.events import build_event
from app.streaming.publisher import InProcessEventPublisher
from app.streaming.store import InMemoryRunEventStore
from app.streaming.websocket import build_stream_router


def _seed(store: InMemoryRunEventStore, run_id: str, count: int) -> None:
    """Synchronously seed `count` events (seq 1..count) for a run."""

    async def go() -> None:
        for seq in range(1, count + 1):
            await store.append(
                build_event({"type": "contribution"}, session_id="s", run_id=run_id, seq=seq)
            )

    asyncio.run(go())


def _app(store: InMemoryRunEventStore, publisher: InProcessEventPublisher) -> FastAPI:
    app = FastAPI()
    app.include_router(build_stream_router(store, publisher))
    return app


def test_connect_replays_full_history_when_after_seq_zero() -> None:
    store = InMemoryRunEventStore()
    _seed(store, "run", 3)
    client = TestClient(_app(store, InProcessEventPublisher()))

    with client.websocket_connect("/sessions/s/stream?run_id=run&after_seq=0") as ws:
        seqs = [ws.receive_json()["seq"] for _ in range(3)]

    assert seqs == [1, 2, 3]


def test_reconnect_replays_only_missed_events() -> None:
    """Client that already saw seq 2 reconnects with after_seq=2 → gets 3,4 only."""
    store = InMemoryRunEventStore()
    _seed(store, "run", 4)
    client = TestClient(_app(store, InProcessEventPublisher()))

    with client.websocket_connect("/sessions/s/stream?run_id=run&after_seq=2") as ws:
        seqs = [ws.receive_json()["seq"] for _ in range(2)]

    assert seqs == [3, 4]
