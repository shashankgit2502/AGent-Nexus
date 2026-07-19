"""Run-event log + replay — the ``run_events`` projection (ARCH §24.8, TECHNICAL §11.4).

ARCH §24.8: on reconnect a client sends the last ``seq`` it saw and the server
**replays missed events** before resuming the live stream. That requires a durable,
ordered, queryable log of every emitted event per run — TECHNICAL §11.4's
``run_events`` table (append-only, ``UNIQUE(run_id, seq)``).

Boundary with Step 9 (R6 — build only this step)
------------------------------------------------
The durable Postgres-backed ``run_events`` table is created by the **Step 9**
Alembic migration (the full multi-tenant schema + RLS lands there, TECHNICAL §11).
To keep Step 8 self-contained and testable *now* without pulling Step 9's schema
forward, the log is defined as a :class:`RunEventStore` **Protocol** with an
in-memory implementation. Replay semantics (ARCH §24.8) are fully implemented and
tested against it; swapping in a ``PostgresRunEventStore`` in Step 9 is a one-line
composition change because every consumer depends on the Protocol, not the impl.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol, runtime_checkable

from app.streaming.events import AGUIEvent


@runtime_checkable
class RunEventStore(Protocol):
    """Durable, ordered, per-run event log backing reconnect/replay (ARCH §24.8)."""

    async def append(self, event: AGUIEvent) -> None:
        """Persist one envelope. Ordering is by the event's ``seq`` within its run."""
        ...

    async def replay(self, run_id: str, after_seq: int = 0) -> list[AGUIEvent]:
        """Return this run's events with ``seq > after_seq``, ascending by ``seq``.

        ``after_seq=0`` (the default) replays the whole run, since ``seq`` is
        1-based (the first emitted event is ``seq=1``).
        """
        ...

    async def last_seq(self, run_id: str) -> int:
        """Highest ``seq`` persisted for the run, or ``0`` if none.

        Used to continue the monotonic sequence across a HITL pause/resume: a
        resuming emitter starts numbering after the last persisted event so the
        whole run shares one strictly-increasing ``seq`` space (ARCH §24.3).
        """
        ...


class InMemoryRunEventStore:
    """In-process :class:`RunEventStore` for single-replica dev and tests.

    Backed by a per-run list. Because the asyncio event loop is single-threaded
    and the methods have no ``await`` points between read and write, each operation
    is effectively atomic — no lock is needed for correctness within one process.
    Cross-process durability (and replay after a server restart) is what the
    Step-9 Postgres-backed store adds.
    """

    def __init__(self) -> None:
        self._by_run: dict[str, list[AGUIEvent]] = defaultdict(list)

    async def append(self, event: AGUIEvent) -> None:
        self._by_run[event["run_id"]].append(event)

    async def replay(self, run_id: str, after_seq: int = 0) -> list[AGUIEvent]:
        return [e for e in self._by_run.get(run_id, []) if e["seq"] > after_seq]

    async def last_seq(self, run_id: str) -> int:
        events = self._by_run.get(run_id)
        return events[-1]["seq"] if events else 0
