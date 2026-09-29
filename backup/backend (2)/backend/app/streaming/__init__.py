"""AG-UI streaming layer (ARCHITECTURE.md §24).

Turns a collaboration-graph run into the typed AG-UI event stream the frontend
renders, with durable replay and cross-replica fan-out:

* :mod:`events`     — the locked envelope + catalog (§24.3/§24.4).
* :mod:`store`      — ``run_events`` log + replay (§24.8).
* :mod:`publisher`  — Redis / in-process live fan-out (§24.5).
* :mod:`emitter`    — seq + persist + publish choke point (§24.3).
* :mod:`runner`     — drives ``graph.astream`` → events (§21.4).
* :mod:`websocket`  — the ``WS /sessions/{id}/stream`` endpoint (§24.2/§24.8).
"""

from __future__ import annotations

from app.streaming.emitter import RunEventEmitter
from app.streaming.events import AGUI_EVENT_TYPES, AGUIEvent, UnknownEventType, build_event
from app.streaming.publisher import (
    EventPublisher,
    InProcessEventPublisher,
    RedisEventPublisher,
    channel_for,
)
from app.streaming.runner import stream_run
from app.streaming.store import InMemoryRunEventStore, RunEventStore
from app.streaming.websocket import build_stream_router

__all__ = [
    "AGUI_EVENT_TYPES",
    "AGUIEvent",
    "EventPublisher",
    "InMemoryRunEventStore",
    "InProcessEventPublisher",
    "RedisEventPublisher",
    "RunEventEmitter",
    "RunEventStore",
    "UnknownEventType",
    "build_event",
    "build_stream_router",
    "channel_for",
    "stream_run",
]
