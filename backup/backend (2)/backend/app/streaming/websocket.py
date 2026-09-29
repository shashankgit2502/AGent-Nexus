"""AG-UI WebSocket endpoint — replay-then-live stream (ARCH §24.2/§24.8).

Transport (ARCH §24.2): server→client AG-UI events over a WebSocket at
``WS /sessions/{session_id}/stream``. WebSocket is preferred over SSE because it is
bidirectional (a later step routes inline HITL decisions back over the same socket;
for now decisions also have the ``POST /sessions/{id}/resume`` path).

Reconnection / replay (ARCH §24.8)
----------------------------------
On (re)connect the client passes the last ``seq`` it saw as ``?after_seq=N``. The
handler first **replays** missed events from the durable log
(:class:`~app.streaming.store.RunEventStore`), then **subscribes** to the live
fan-out (:class:`~app.streaming.publisher.EventPublisher`) and forwards new events.
Live events with ``seq <= last replayed`` are skipped, so the replay/live boundary
never double-delivers (idempotent by ``seq``) even if an event lands during the
hand-off.

Composition note (R6): mounting this router and the run-launch REST endpoint
(``POST /sessions/{id}/run``) into the app, plus resolving ``run_id`` from the DB,
is Step 9 (FastAPI routes). This module provides the endpoint as a factory taking
its two collaborators explicitly, so it is unit-testable now and trivially mounted
later. ``app/main.py`` wires a process-local store + publisher for the dev/demo
acceptance check.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.streaming.publisher import EventPublisher
from app.streaming.store import RunEventStore

logger = logging.getLogger(__name__)


def build_stream_router(store: RunEventStore, publisher: EventPublisher) -> APIRouter:
    """Build the AG-UI WebSocket router bound to a store + publisher.

    Args:
        store: durable per-run event log for reconnect replay (ARCH §24.8).
        publisher: live fan-out the run driver publishes to (ARCH §24.5).
    """
    router = APIRouter()

    async def replay_then_live(websocket: WebSocket, *, run_id: str, after_seq: int) -> None:
        """Replay missed events (by ``seq``), then forward the live stream (§24.8).

        Closes over ``store`` + ``publisher``. Both the session and conversation
        streams key off ``run_id`` (a team-chat turn is run-per-turn), so they share
        this one body and the same dedup at the replay/live hand-off boundary.
        """
        await websocket.accept()
        # Subscribe FIRST, then replay: a run now streams **live** (ARCH §24.5), so a
        # client connecting mid-run must not lose events emitted between the replay
        # query and the live subscription. The emitter appends to the store *before*
        # publishing, so subscribing up-front + deduping by ``seq`` makes the handoff
        # exact — any event published during replay is buffered and delivered once.
        live = publisher.subscribe(run_id)
        try:
            last_sent = after_seq
            for event in await store.replay(run_id, after_seq):
                await websocket.send_json(event)
                last_sent = event["seq"]
            async for event in live:
                if event["seq"] <= last_sent:
                    continue
                await websocket.send_json(event)
                last_sent = event["seq"]
        except WebSocketDisconnect:
            logger.debug("client disconnected from run=%s stream", run_id)
        finally:
            await live.aclose()

    @router.websocket("/sessions/{session_id}/stream")
    async def stream(  # pyright: ignore[reportUnusedFunction]
        websocket: WebSocket,
        session_id: str,
        run_id: str,
        after_seq: int = 0,
    ) -> None:
        """Stream one run's AG-UI events: replay missed, then live (ARCH §24.8)."""
        await replay_then_live(websocket, run_id=run_id, after_seq=after_seq)

    @router.websocket("/conversations/{conversation_id}/stream")
    async def conversation_stream(  # pyright: ignore[reportUnusedFunction]
        websocket: WebSocket,
        conversation_id: str,
        run_id: str,
        after_seq: int = 0,
    ) -> None:
        """Stream a team-chat turn's AG-UI events (ARCH §8.5.4 / §24.8).

        Identical to the session stream — keyed by ``run_id`` — so a conversation
        turn can be expanded into the Session Workspace using the same renderer.
        """
        await replay_then_live(websocket, run_id=run_id, after_seq=after_seq)

    return router
