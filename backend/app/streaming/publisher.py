"""Live event fan-out across FastAPI replicas (ARCH §24.5).

A run executes on **one** FastAPI replica, but a client's WebSocket may be
connected to **another**. ARCH §24.5: the executing node publishes each event to
**Redis pub/sub** on channel ``run:{run_id}``; every replica's WebSocket handler
subscribes to that channel and forwards to its connected clients. Redis here is
*only* a UI-event bus + cache — **never** an inter-agent transport (that stays the
in-process blackboard, locked decision).

> "Single-replica dev needs no Redis." (ARCH §24.5)

So this module ships two interchangeable implementations behind one
:class:`EventPublisher` Protocol:

* :class:`InProcessEventPublisher` — asyncio fan-out within one process (default
  for local dev / tests); no external dependency.
* :class:`RedisEventPublisher` — real cross-replica fan-out via ``redis.asyncio``
  (R1-verified against redis 8.0: ``Redis.publish`` / ``Redis.pubsub`` /
  ``PubSub.listen``).

Both ``subscribe`` methods are **async generators**: ``async for event in
publisher.subscribe(run_id): ...``. They run until the consumer stops iterating
(WebSocket disconnect), at which point the generator's ``finally`` cleans up.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from app.streaming.events import AGUIEvent

if TYPE_CHECKING:
    from redis.asyncio import Redis


def channel_for(run_id: str) -> str:
    """Pub/sub channel name for a run (ARCH §24.5: ``run:{run_id}``)."""
    return f"run:{run_id}"


@runtime_checkable
class EventPublisher(Protocol):
    """Publishes AG-UI envelopes and lets WebSocket handlers subscribe per run."""

    async def publish(self, event: AGUIEvent) -> None:
        """Fan one envelope out to every current subscriber of its run."""
        ...

    def subscribe(self, run_id: str) -> AsyncGenerator[AGUIEvent, None]:
        """Yield live envelopes for ``run_id`` until the consumer stops iterating."""
        ...


class InProcessEventPublisher:
    """asyncio in-process fan-out (no Redis) — single-replica dev / tests (ARCH §24.5).

    Each ``subscribe`` registers an :class:`asyncio.Queue`; ``publish`` pushes the
    event onto every live subscriber's queue (non-blocking). The queue decouples
    the producer (the graph stream driver) from each slow consumer (a WebSocket).
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[AGUIEvent]]] = defaultdict(set)

    async def publish(self, event: AGUIEvent) -> None:
        # Snapshot to a list so a subscriber unregistering mid-iteration is safe.
        for queue in list(self._subscribers.get(event["run_id"], ())):
            queue.put_nowait(event)

    def subscribe(self, run_id: str) -> AsyncGenerator[AGUIEvent, None]:
        """Register a subscriber **eagerly** and return its live iterator.

        Registration happens the moment ``subscribe`` is called — *before* the
        caller starts iterating — so the WebSocket handler can subscribe first and
        then replay the store with no lost-event window at the replay→live handoff
        (events published during replay are buffered on the queue, deduped by seq).
        A sync method (not an ``async def`` generator) is what makes the queue
        register up-front rather than on first ``__anext__``.
        """
        queue: asyncio.Queue[AGUIEvent] = asyncio.Queue()
        self._subscribers[run_id].add(queue)

        async def _iter() -> AsyncGenerator[AGUIEvent, None]:
            try:
                while True:
                    yield await queue.get()
            finally:
                # Consumer stopped (WebSocket closed) → deregister and drop empty sets.
                self._subscribers[run_id].discard(queue)
                if not self._subscribers[run_id]:
                    self._subscribers.pop(run_id, None)

        return _iter()


class RedisEventPublisher:
    """Cross-replica fan-out via ``redis.asyncio`` pub/sub (ARCH §24.5).

    The same envelope JSON is published to ``run:{run_id}``; any replica subscribed
    to that channel forwards it to its WebSocket clients. Inter-agent state never
    travels this bus — only UI events (locked decision).
    """

    def __init__(self, client: Redis) -> None:
        self._redis = client

    async def publish(self, event: AGUIEvent) -> None:
        await self._redis.publish(channel_for(event["run_id"]), json.dumps(event))

    async def subscribe(self, run_id: str) -> AsyncGenerator[AGUIEvent, None]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel_for(run_id))
        try:
            async for message in pubsub.listen():
                # listen() also yields subscribe/unsubscribe control frames; only
                # forward actual published payloads.
                if message.get("type") != "message":
                    continue
                yield cast(AGUIEvent, json.loads(message["data"]))
        finally:
            await pubsub.unsubscribe(channel_for(run_id))
            await pubsub.aclose()  # type: ignore[no-untyped-call]  # redis PubSub.aclose is untyped upstream
