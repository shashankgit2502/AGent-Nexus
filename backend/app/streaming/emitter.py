"""RunEventEmitter — the single choke point for emitting AG-UI events (ARCH §24).

Every event for a run goes through one emitter so three invariants always hold
together (ARCH §24.3/§24.5/§24.8):

1. **Monotonic ``seq``** — assigned here, strictly increasing per run, so clients
   can order and request "everything after seq N" on reconnect.
2. **Durable log** — appended to the :class:`~app.streaming.store.RunEventStore`
   for replay.
3. **Live fan-out** — published to the
   :class:`~app.streaming.publisher.EventPublisher` for connected clients.

Doing all three in one place means a node can never publish without persisting (or
vice-versa), and ``seq`` can never diverge from what was stored.

Resume continuity
-----------------
A HITL pause/resume runs the stream driver twice for one logical run. ``seq`` must
stay monotonic across both. :meth:`for_run` reads the store's ``last_seq`` so a
resuming emitter continues numbering after the last persisted event rather than
restarting at 1.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from app.streaming.events import AGUIEvent, build_event
from app.streaming.publisher import EventPublisher
from app.streaming.store import RunEventStore


class RunEventEmitter:
    """Assign ``seq``, persist, and publish one run's events (ARCH §24)."""

    def __init__(
        self,
        *,
        session_id: str,
        run_id: str,
        store: RunEventStore,
        publisher: EventPublisher,
        start_seq: int = 0,
    ) -> None:
        self._session_id = session_id
        self._run_id = run_id
        self._store = store
        self._publisher = publisher
        self._seq = start_seq
        # Serialise emits so `seq` assignment, the durable append, and the live
        # publish are atomic per event. Live tool/reasoning streaming (Bug 5) emits
        # from **parallel** agent turns concurrently; without this, two emits could
        # publish out of `seq` order and the client reducer — which drops any event
        # whose `seq` is not greater than the last seen — would silently lose one.
        self._lock = asyncio.Lock()

    @classmethod
    async def for_run(
        cls,
        *,
        session_id: str,
        run_id: str,
        store: RunEventStore,
        publisher: EventPublisher,
    ) -> RunEventEmitter:
        """Build an emitter continuing the run's existing ``seq`` (resume-safe).

        Reads ``store.last_seq(run_id)`` so a fresh run starts at ``seq=1`` and a
        resume after HITL continues after the last persisted event.
        """
        start_seq = await store.last_seq(run_id)
        return cls(
            session_id=session_id,
            run_id=run_id,
            store=store,
            publisher=publisher,
            start_seq=start_seq,
        )

    async def emit(self, raw: Mapping[str, Any]) -> AGUIEvent:
        """Promote a raw ``{type, data}`` record to an envelope, persist, publish.

        Returns the built envelope (useful in tests / for the caller to inspect).
        ``build_event`` validates the type against the locked catalog first, so an
        unknown type raises before anything is stored or published.
        """
        async with self._lock:
            self._seq += 1
            event = build_event(
                raw,
                session_id=self._session_id,
                run_id=self._run_id,
                seq=self._seq,
            )
            await self._store.append(event)
            await self._publisher.publish(event)
            return event

    @property
    def last_seq(self) -> int:
        """The most recently assigned ``seq`` (0 before the first emit)."""
        return self._seq
