"""Startup recovery for orphaned runs (durability — ARCH §24.5/§24.8).

A run executes on a background asyncio task (``run_service.spawn_run``). If the
process stops while a task is in flight — restart, crash, force-kill on
``--reload``, deploy — the task dies but its ``runs`` row stays ``status='running'``
forever and **no terminal AG-UI event is ever emitted**. A client (re)connecting
to that run over ``WS /sessions/{id}/stream`` replays the partial event log
(e.g. ``run_start`` + N×``agent_turn_start``) and then blocks on the live
subscription with nothing more ever arriving — the Workspace freezes on
"thinking" indefinitely.

This mirrors :func:`app.knowledge.worker.recover_stuck_sources` (the same
durability gap for ingestion): at startup, before serving requests, every run
still marked ``running`` is by definition orphaned — the process that drove it is
gone (any live run lives on an in-process task, not in the DB). We finalize each:
mark it ``failed``, stamp ``finished_at``, and emit a terminal run-scoped
``error`` event through the run's emitter so a reconnecting client's stream
terminates cleanly. Provider/model agnostic: an interrupted run is interrupted
regardless of which model it used.

``paused`` runs are intentionally left alone — they are legitimately suspended at
the HITL gate (``run_service._finalize_run``) awaiting a human decision via
``POST /sessions/{id}/resume``, not orphaned.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import select

from app.db.models import Run
from app.db.session import AsyncSessionLocal
from app.streaming.emitter import RunEventEmitter

logger = logging.getLogger(__name__)

# Terminal-event reason a reconnecting client sees on an orphaned run (§24.4).
_INTERRUPTED_MESSAGE = (
    "Run interrupted: the backend stopped (restart, crash, or reload) before this "
    "run finished. It has been finalized so the stream does not hang."
)


async def recover_orphaned_runs(app: FastAPI) -> int:
    """Finalize runs left ``running`` by a crash/restart (durability, ARCH §24.8).

    Runs once at startup before serving requests. Queries across orgs (no RLS GUC —
    startup, like the org seed and :func:`recover_stuck_sources`; the dev/owner
    connection is not subject to RLS). For each orphan: mark ``failed`` +
    ``finished_at``, then emit a terminal run-scoped ``error`` event so a
    reconnecting client's replay ends on a terminal event instead of freezing.
    Best-effort and fully logged — a recovery failure must never block startup
    (R3: surfaced, not swallowed). Returns the count (for logging/tests).
    """
    async with AsyncSessionLocal() as db:
        orphans = (await db.scalars(select(Run).where(Run.status == "running"))).all()
        for run in orphans:
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
        if orphans:
            await db.commit()

    # Emit the terminal error AFTER the status commit, so the persisted log a
    # reconnecting client replays ends on a terminal event. The store is RLS-scoped
    # per run via register_run (the run_service.fail_run pattern); the in-process
    # publisher has no subscribers yet at startup, so this only needs to *persist*.
    store = app.state.event_store
    publisher = app.state.event_publisher
    for run in orphans:
        try:
            if hasattr(store, "register_run"):
                store.register_run(str(run.id), run.org_id)
            emitter = await RunEventEmitter.for_run(
                session_id=str(run.session_id or run.conversation_id or ""),
                run_id=str(run.id),
                store=store,
                publisher=publisher,
            )
            await emitter.emit(
                {"type": "error", "data": {"scope": "run", "message": _INTERRUPTED_MESSAGE}}
            )
        except Exception:  # noqa: BLE001 — recovery is best-effort; never block startup.
            logger.warning(
                "run-recovery: failed to emit terminal error for orphaned run %s",
                run.id,
                exc_info=True,
            )

    if orphans:
        logger.info("run-recovery: finalized %d orphaned run(s) on startup", len(orphans))
    return len(orphans)
