"""Cooperative run cancellation (ARCHITECTURE.md §21.6).

The problem
-----------
A run executes on a background ``asyncio.Task`` and, until now, could not be stopped. At
team sizes ≥ 7 that is not survivable: a 12-agent × 3-round run is ~110 model calls, so an
unstoppable run is unbounded spend with no exit. A HITL-paused run had the same problem from
the other direction — it waits for a human forever and cancellation was its only possible
exit.

Why this is not just ``task.cancel()``
--------------------------------------
LangGraph checkpoints at **node/task completion**, not continuously. A hard cancel therefore
throws away everything since the last node boundary — the user watches output stream, hits
stop, and it vanishes. Worse, cancelling an outer graph can leave an inner ``ainvoke`` still
running, and an inner ``ainvoke`` is exactly the shape of a mesh agent turn — so a "stopped"
run would keep calling models and keep billing. (LangGraph Platform solves this with
``runs.cancel(action=...)``; a self-hosted deployment does not get that API and has to build
this seam, which is what this module is.)

So cancellation is **cooperative first, forced second**:

1. the request marks the run ``cancelling`` (durable, survives a restart, visible to any
   replica) and sets an in-process flag (instant on the executing replica);
2. the graph checks that flag at points where its state **is** checkpointed — the
   ``stream_run`` super-step boundary and ``agent_turn`` entry — and stops cleanly;
3. only if the run is still alive after a grace period is the task force-cancelled, for the
   case where a turn is blocked inside a model call and cannot reach a checkpoint.

Client disconnect is deliberately **not** cancellation: the Workspace is built for
reconnect-and-replay (§24.8), so closing a tab must leave the run executing.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

#: Durable statuses. ``cancelling`` is the in-flight signal; ``cancelled`` is terminal.
#: ``runs.status`` is unconstrained TEXT (only the owner XOR is a CHECK), so these need no
#: migration and older rows are unaffected.
STATUS_CANCELLING = "cancelling"
STATUS_CANCELLED = "cancelled"

#: Statuses a run can be cancelled *from*. ``paused`` is included deliberately: a run waiting
#: at the human gate has no other exit, and leaving it pending forever is the failure mode
#: cancellation exists to fix.
CANCELLABLE_STATUSES = frozenset({"running", "paused", STATUS_CANCELLING})


def _cancelled_runs(app: FastAPI) -> set[UUID]:
    """The in-process set of runs asked to stop on *this* replica.

    Created lazily so an app built before this feature (or a test double) still works.
    """
    existing = getattr(app.state, "cancelled_runs", None)
    if existing is None:
        existing = set()
        app.state.cancelled_runs = existing
    return existing


def request_cancel(app: FastAPI, run_id: UUID) -> None:
    """Flag a run as cancel-requested on this replica (the fast, in-process path)."""
    _cancelled_runs(app).add(run_id)


def clear_cancel(app: FastAPI, run_id: UUID) -> None:
    """Drop a run's in-process flag once it has finalised, so the set cannot grow forever."""
    _cancelled_runs(app).discard(run_id)


def is_cancel_requested(app: FastAPI, run_id: UUID) -> bool:
    """Whether this replica has been asked to stop ``run_id``."""
    return run_id in _cancelled_runs(app)


class CancelSignal:
    """The check the graph performs at each safe stopping point.

    Two sources, cheapest first:

    * **in-process flag** — set by :func:`request_cancel` when the cancel lands on the replica
      that is executing the run. No I/O, so it can be checked at every boundary.
    * **durable status poll** — reads ``runs.status`` so a cancel that landed on a *different*
      replica is still honoured. Throttled by ``poll_interval_s`` because node boundaries can
      be seconds apart; the query is negligible next to a model call, but it should not run in
      a tight loop.

    Once observed, the result is latched: a run that has been told to stop never un-stops, so
    later checks are free and cannot flip back mid-teardown.
    """

    def __init__(
        self,
        *,
        run_id: UUID,
        is_flagged: Callable[[], bool],
        load_status: Callable[[], Any] | None = None,
        poll_interval_s: float = 5.0,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._run_id = run_id
        self._is_flagged = is_flagged
        self._load_status = load_status
        self._poll_interval_s = poll_interval_s
        self._now = now
        self._latched = False
        self._last_poll = 0.0

    async def __call__(self) -> bool:
        """True when this run has been asked to stop (latched once true)."""
        if self._latched:
            return True
        if self._is_flagged():
            self._latched = True
            logger.info("run %s: cancellation observed (in-process flag)", self._run_id)
            return True
        if self._load_status is None:
            return False

        elapsed = self._now() - self._last_poll
        if elapsed < self._poll_interval_s:
            return False
        self._last_poll = self._now()
        try:
            status = await self._load_status()
        except Exception:  # noqa: BLE001 — a failed poll must never abort a healthy run.
            # Degrade to "not cancelled": a transient DB blip should not kill work in
            # progress. The in-process path still covers the common case, and the next
            # poll retries.
            logger.warning("run %s: cancellation status poll failed", self._run_id, exc_info=True)
            return False
        if status in (STATUS_CANCELLING, STATUS_CANCELLED):
            self._latched = True
            logger.info("run %s: cancellation observed (durable status=%s)", self._run_id, status)
            return True
        return False
