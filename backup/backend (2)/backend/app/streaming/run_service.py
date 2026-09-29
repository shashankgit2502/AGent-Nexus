"""Run orchestration service — launch & resume (ARCH §21.4, §8, §8.5).

Bridges the DB (sessions/runs/artifacts), the collaboration graph
(``build_collab_graph``), and the AG-UI streaming layer (``stream_run`` + emitter).
The session router stays thin (R5) by delegating here.

Flow (ARCH §21.4):
  create ``runs`` row → build graph + emitter + (real|stub) MeshContext → drive
  ``stream_run`` (events persisted to ``run_events`` + fanned out) → finalize the
  run row + persist the ``artifacts`` row from the final blackboard state.

Lightweight vs deep (ARCH §8.5): ``deep_collaborate=False`` runs the **same** graph
with ``max_rounds=1`` and HITL off (one parallel round → straight to synthesis);
``True`` runs the full multi-round loop with the human gate.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.snapshot import (
    build_mesh_context,
    load_active_agent_ids,
    load_agent_names,
    load_team_success_criteria,
)
from app.core.config import get_settings
from app.core.identity import OrgContext
from app.db.models import Artifact, Run
from app.db.models import Session as SessionModel
from app.db.repositories import OrgScopedRepository
from app.db.session import AsyncSessionLocal
from app.graph.build import build_collab_graph
from app.graph.state import initial_collab_state
from app.schemas.sessions import ResumeRequest, RunLaunch
from app.streaming.cancellation import (
    CANCELLABLE_STATUSES,
    STATUS_CANCELLED,
    STATUS_CANCELLING,
    CancelSignal,
    clear_cancel,
    is_cancel_requested,
    request_cancel,
)
from app.streaming.emitter import RunEventEmitter
from app.streaming.usage import new_usage_callback, record_usage, summarize

logger = logging.getLogger(__name__)

# Terminal artifact for a human-stopped run (§21.6). A distinct kind from ``rejected``
# (the human read the answer and refused it) and from a failure — History must be able to
# tell "I stopped this" from "this broke".
_KIND_CANCELLED = "cancelled"
_CANCELLED_NOTICE = "Run cancelled by the user before it produced a final output."

# An optional post-completion hook run in the background task's own session, after
# the run finalises — used by chat to fill the assistant message from the artifact.
OnComplete = Callable[[AsyncSession, "LaunchResult"], Awaitable[None]]


class LaunchResult:
    """Outcome of a launch/resume: the run row, whether it paused, and the last seq."""

    def __init__(self, run: Run, interrupted: bool, last_seq: int) -> None:
        self.run = run
        self.interrupted = interrupted
        self.last_seq = last_seq


async def launch_run(
    *, app: FastAPI, db: AsyncSession, org: OrgContext, session: SessionModel, payload: RunLaunch
) -> LaunchResult:
    """Create a run and start driving it **in the background** (ARCH §21.4, §24.5).

    The graph executes independently of this request so clients connect over the WS
    *while it runs* and watch the live stream (the locked design — §24.5 says a run
    executes on one replica while a client may be attached to another). We persist
    the ``runs`` row, return its id immediately, and hand execution to a background
    task with its own RLS-scoped session.
    """
    # Lightweight path parameters (ARCH §8.5): single round, no human gate.
    deep = payload.deep_collaborate
    max_rounds = payload.max_rounds if deep else 1
    # Per-peer prompt compression budget (config.py): shrinks rounds ≥ 2 to keep each
    # request under the provider rate limit. 0 = unchanged (no cap).
    settings = get_settings()

    run = Run(
        org_id=org.org_id,
        session_id=session.id,
        query=payload.query,
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.flush()
    # Commit so the run row is visible to the background task's own session, the
    # event store (FK for run_events), and any WS client connecting mid-run.
    await db.commit()

    agent_ids = await load_active_agent_ids(db, org_id=org.org_id, team_id=session.team_id)
    state = initial_collab_state(
        # Scope this run's blackboard writes (ARCH §22.5). A session's ``thread_id`` is
        # reused by every run on it, so without this the second run on a session collides
        # with the first: the agent_turn idempotency guard skips every agent and consensus
        # ranks the previous run's contributions.
        run_id=str(run.id),
        goal=payload.query,
        active_agent_ids=agent_ids,
        # The team's configured success criteria now actually reach the run: the
        # orchestrator plans against them, every round prompt renders them, the
        # synthesizer merges against them, and the producer builds to them.
        success_criteria=await load_team_success_criteria(
            db, org_id=org.org_id, team_id=session.team_id
        ),
        max_rounds=max_rounds,
        confidence_threshold=payload.confidence_threshold,
        hitl_enabled=deep,
        peer_content_max_chars=settings.AGENT_PEER_CONTENT_MAX_CHARS,
        # Display names for readable plan framing (ids alone make briefs unreadable).
        agent_names=await load_agent_names(db, org_id=org.org_id, team_id=session.team_id),
    )
    spawn_run(
        app=app,
        org=org,
        run_id=run.id,
        stream_id=str(session.id),
        team_id=session.team_id,
        thread_id=session.thread_id,
        graph_input=state,
    )
    # interrupted is no longer known synchronously — the client learns of the HITL
    # gate from the live ``hitl_request`` event (ARCH §24.4), not this response.
    return LaunchResult(run=run, interrupted=False, last_seq=0)


async def resume_run(
    *,
    app: FastAPI,
    db: AsyncSession,
    org: OrgContext,
    session: SessionModel,
    run: Run,
    payload: ResumeRequest,
) -> LaunchResult:
    """Resume a HITL-paused run with the human's decision, in the background (ARCH §4.5)."""
    decision: dict[str, Any] = {"type": payload.decision}
    if payload.content is not None:
        decision["content"] = payload.content
    if payload.reason is not None:
        decision["reason"] = payload.reason
    run.status = "running"
    await db.commit()
    spawn_run(
        app=app,
        org=org,
        run_id=run.id,
        stream_id=str(session.id),
        team_id=session.team_id,
        thread_id=session.thread_id,
        graph_input=Command(resume=decision),
    )
    return LaunchResult(run=run, interrupted=False, last_seq=0)


def spawn_run(
    *,
    app: FastAPI,
    org: OrgContext,
    run_id: UUID,
    stream_id: str,
    team_id: UUID,
    thread_id: str,
    graph_input: Any,
    on_complete: OnComplete | None = None,
) -> asyncio.Task[None]:
    """Schedule background execution of a run and track the task (ARCH §24.5).

    The mesh run is driven on a background task; see :func:`spawn_background` for
    the registry + run→org registration shared with the no-team chat path.
    """
    return spawn_background(
        app,
        org=org,
        run_id=run_id,
        coro=_execute_run(
            app=app,
            org=org,
            run_id=run_id,
            stream_id=stream_id,
            team_id=team_id,
            thread_id=thread_id,
            graph_input=graph_input,
            on_complete=on_complete,
        ),
    )


def spawn_background(
    app: FastAPI, *, org: OrgContext, run_id: UUID, coro: Coroutine[Any, Any, None]
) -> asyncio.Task[None]:
    """Schedule a background run task, tracked + RLS-registered (ARCH §24.5).

    Shared by the mesh path (:func:`spawn_run`) and the no-team chat stream. Three
    invariants:

    * the run→org mapping is registered **synchronously**, before the task is
      scheduled — a WS client may connect (and replay) the instant the launch POST
      returns, *before* the task starts, so the RLS-scoped event store must already
      know this run's org (else ``replay`` raises ``RunOrgUnknown``);
    * the task is strongly referenced in ``app.state.run_tasks`` until it finishes
      (asyncio only weakly references tasks, so an untracked task can be GC'd
      mid-flight); the lifespan awaits any in-flight tasks on shutdown;
    * the reference is **keyed by run id** (§21.6) so cancellation has a handle it can
      address. A bare set had nothing for ``POST /runs/{id}/cancel`` to reach, which is
      why a run could not be stopped at all.
    """
    event_store = app.state.event_store
    if hasattr(event_store, "register_run"):
        event_store.register_run(str(run_id), org.org_id)

    tasks: dict[UUID, asyncio.Task[None]] = app.state.run_tasks
    task = asyncio.create_task(coro)
    tasks[run_id] = task

    def _release(_: asyncio.Task[None]) -> None:
        # Compare identity before removing: a relaunch/resume on the same run id may have
        # replaced the entry, and a finishing older task must not evict the live one.
        if tasks.get(run_id) is task:
            tasks.pop(run_id, None)
        clear_cancel(app, run_id)

    task.add_done_callback(_release)
    return task


async def _execute_run(
    *,
    app: FastAPI,
    org: OrgContext,
    run_id: UUID,
    stream_id: str,
    team_id: UUID,
    thread_id: str,
    graph_input: Any,
    on_complete: OnComplete | None,
) -> None:
    """Run the graph to completion/pause on its own RLS-scoped session (ARCH §24.5).

    This is the background body. It owns a fresh ``AsyncSession`` (the request's
    session is gone by now), sets the org GUC for RLS, drives the run, then runs the
    optional ``on_complete`` hook. Any failure is **surfaced** as an ``error`` event
    and a ``failed`` run row (never silently swallowed, R3) so the client's stream
    terminates rather than hanging forever.
    """
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("SELECT set_config('app.current_org', :org, false)"),
            {"org": str(org.org_id)},
        )
        try:
            run = await OrgScopedRepository(db, Run, org.org_id).get(run_id)
            if run is None:  # pragma: no cover — committed just before spawn
                raise RuntimeError(f"run {run_id} vanished before background execution")
            result = await drive_run(
                app=app,
                db=db,
                org=org,
                run=run,
                stream_id=stream_id,
                team_id=team_id,
                thread_id=thread_id,
                graph_input=graph_input,
            )
            if on_complete is not None:
                await on_complete(db, result)
                await db.commit()
        except Exception:
            logger.exception("background run %s failed", run_id)
            await fail_run(app, db, org=org, run_id=run_id, stream_id=stream_id)
        finally:
            try:
                await db.execute(text("RESET app.current_org"))
                await db.commit()
            except Exception:
                logger.warning("failed to reset RLS GUC after background run", exc_info=True)


class RunNotCancellable(RuntimeError):
    """The run is already terminal, so there is nothing to stop (§21.6)."""


async def cancel_run(
    app: FastAPI, db: AsyncSession, *, org: OrgContext, run: Run, stream_id: str
) -> Run:
    """Stop a running (or HITL-paused) run — cooperative first, forced second (§21.6).

    Order matters, and each step exists for a reason:

    1. **Persist ``cancelling`` first.** This is the durable signal: it survives a restart,
       it is what a cancel landing on another replica leaves behind, and it is what the
       graph's throttled status poll reads. Setting the in-process flag without persisting
       would lose the request on any restart.
    2. **Set the in-process flag.** Instant on the replica actually executing the run; the
       graph stops at its next checkpointed boundary rather than mid-node.
    3. **Give it a grace period.** A turn already inside a model call cannot reach a
       boundary until that call returns. Waiting lets the common case shut down cleanly,
       preserving the checkpoint.
    4. **Force-cancel only if still alive.** Last resort, because a hard cancel discards
       un-checkpointed state and can leave an inner ``ainvoke`` running.
    5. **Finalise unconditionally.** A cancelled run must reach a terminal state and emit a
       terminal event — otherwise a connected client hangs forever, which is precisely the
       bug ``run_recovery`` exists to fix.

    A run that is already ``completed``/``failed``/``cancelled`` raises
    :class:`RunNotCancellable`; the route maps that to a 409 so a double-click is a
    no-op rather than a 500 or a corrupted row.
    """
    if run.status not in CANCELLABLE_STATUSES:
        raise RunNotCancellable(run.status)

    settings = get_settings()
    run.status = STATUS_CANCELLING
    await db.commit()
    request_cancel(app, run.id)
    logger.info("run %s: cancellation requested (was %s)", run.id, run.status)

    task: asyncio.Task[None] | None = app.state.run_tasks.get(run.id)
    if task is not None and not task.done():
        try:
            await asyncio.wait_for(
                asyncio.shield(task), timeout=settings.RUN_CANCEL_GRACE_S
            )
        except TimeoutError:
            # Still inside a model call after the grace period — force it. Logged at
            # WARNING because this path *does* lose un-checkpointed work (§21.6).
            logger.warning(
                "run %s: cooperative cancel timed out after %.0fs; forcing task cancel",
                run.id,
                settings.RUN_CANCEL_GRACE_S,
            )
            task.cancel()
        except Exception:  # noqa: BLE001 — the task's own failure is finalised below.
            logger.info("run %s: task ended during cancellation", run.id, exc_info=True)

    await _finalize_cancelled(app, db, org=org, run=run, stream_id=stream_id)
    return run


async def _finalize_cancelled(
    app: FastAPI, db: AsyncSession, *, org: OrgContext, run: Run, stream_id: str
) -> None:
    """Mark a cancelled run terminal and close its stream (§21.6 step 5).

    Emits ``run_finished`` with a ``cancelled`` artifact rather than an ``error``: the run
    did not fail, a human stopped it, and the History view must be able to tell those apart.

    Runs on a fresh transaction and never raises — this is the last step before the client's
    stream would otherwise hang, so a bookkeeping failure here must not prevent the terminal
    event from being attempted.
    """
    try:
        await db.rollback()
        current = await OrgScopedRepository(db, Run, org.org_id).get(run.id)
        if current is not None:
            current.status = STATUS_CANCELLED
            current.finished_at = datetime.now(UTC)
            db.add(
                Artifact(
                    org_id=current.org_id,
                    run_id=current.id,
                    kind=_KIND_CANCELLED,
                    content=_CANCELLED_NOTICE,
                    content_format="markdown",
                )
            )
            await db.commit()
    except Exception:
        logger.exception("failed to finalize cancelled run %s", run.id)

    try:
        emitter = await RunEventEmitter.for_run(
            session_id=stream_id,
            run_id=str(run.id),
            store=app.state.event_store,
            publisher=app.state.event_publisher,
        )
        await emitter.emit(
            {
                "type": "run_finished",
                "data": {
                    "artifact": {
                        "kind": _KIND_CANCELLED,
                        "content": _CANCELLED_NOTICE,
                        "content_format": "markdown",
                    }
                },
            }
        )
    except Exception:
        logger.exception("failed to emit terminal event for cancelled run %s", run.id)
    finally:
        clear_cancel(app, run.id)


async def fail_run(
    app: FastAPI, db: AsyncSession, *, org: OrgContext, run_id: UUID, stream_id: str
) -> None:
    """Mark a crashed run failed and emit a terminal ``error`` event (ARCH §24.4).

    Shared by the mesh background executor and the no-team chat stream.
    """
    try:
        await db.rollback()
        run = await OrgScopedRepository(db, Run, org.org_id).get(run_id)
        if run is not None:
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            await db.commit()
        emitter = await RunEventEmitter.for_run(
            session_id=stream_id,
            run_id=str(run_id),
            store=app.state.event_store,
            publisher=app.state.event_publisher,
        )
        await emitter.emit({"type": "error", "data": {"scope": "run", "message": "run failed"}})
    except Exception:
        logger.exception("failed to finalize the failed run %s", run_id)


async def drive_run(
    *,
    app: FastAPI,
    db: AsyncSession,
    org: OrgContext,
    run: Run,
    stream_id: str,
    team_id: UUID,
    thread_id: str,
    graph_input: Any,
) -> LaunchResult:
    """Shared launch/resume body: build collaborators, stream, finalize.

    Owner-agnostic (ARCH §8.5): the run is driven the same way whether it belongs to
    a launched **Session** or a chat **Conversation** — only the binding differs.

    Args:
        run: the already-persisted ``runs`` row (bound to its owner via
            ``session_id`` XOR ``conversation_id``).
        stream_id: the AG-UI envelope ``session_id`` field — the stream's owning
            surface (a session id or a conversation id; ARCH §24.3).
        team_id: the team whose agents form the mesh (a no-team conversation never
            reaches here — it uses the single-agent path in :mod:`app.chat.service`).
        thread_id: the LangGraph checkpointer thread carrying multi-turn context.
    """
    settings = get_settings()
    graph = build_collab_graph(app.state.checkpointer, app.state.store)

    event_store = app.state.event_store
    # Bind the run to its org so the RLS-scoped event store can set app.current_org.
    if hasattr(event_store, "register_run"):
        event_store.register_run(str(run.id), org.org_id)

    emitter = await RunEventEmitter.for_run(
        session_id=stream_id,
        run_id=str(run.id),
        store=event_store,
        publisher=app.state.event_publisher,
    )
    context = await build_mesh_context(
        db,
        org_id=org.org_id,
        team_id=team_id,
        store=app.state.store,
        settings=settings,
        # Chat runs are bound to a conversation (run-per-turn, §8.5.2); a launched
        # Session run has no conversation. When set, the conversation's transient
        # uploads become a per-turn `search_uploaded_files` tool (Bug 2, §8.5.3).
        conversation_id=run.conversation_id,
        # Live activity streaming (Bug 5): the mesh node emits each agent's
        # reasoning / tool calls through the run's emitter as they happen.
        emit=emitter.emit,
        # Enables the post-consensus artifact producer (ARTIFACTS §2A) — artifacts are
        # run-scoped, so the producer is wired only when the run id is known.
        run_id=run.id,
    )

    # Token metering (§21.7): ONE handler on the top-level config. LangChain propagates
    # callbacks down the runnable tree, so this captures every model call inside the graph
    # — mesh turns, structured repair, planner, synthesizer, verifier, producer,
    # consolidation — without threading a config through any of those call sites. It must
    # be per-run (never bound at model construction): the resolver caches built models
    # across runs, so a shared handler would cross-attribute concurrent runs.
    usage_callback = new_usage_callback()
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [usage_callback],
    }

    # Cooperative cancellation (§21.6): checked at checkpointed boundaries. The in-process
    # flag is instant on this replica; the throttled status poll picks up a cancel issued
    # elsewhere. Uses its OWN short-lived session so polling never interferes with the
    # run's open transaction.
    cancel_signal = CancelSignal(
        run_id=run.id,
        is_flagged=lambda: is_cancel_requested(app, run.id),
        load_status=lambda: _load_run_status(org.org_id, run.id),
        poll_interval_s=settings.RUN_CANCEL_POLL_S,
    )
    context = replace(context, should_cancel=cancel_signal) if context is not None else None

    from app.streaming.runner import stream_run  # local import avoids an import cycle

    result = await stream_run(
        graph,
        graph_input=graph_input,
        config=config,
        emitter=emitter,
        context=context,
        should_cancel=cancel_signal,
    )

    # A cooperatively-stopped run is finalised by ``cancel_run``, which owns the terminal
    # state and event. Returning early keeps this path from also writing a ``completed``
    # row and a second ``run_finished`` for the same run.
    if result.get("cancelled"):
        logger.info("run %s: stream stopped cooperatively for cancellation", run.id)
        return LaunchResult(run=run, interrupted=False, last_seq=result["last_seq"])

    summary = summarize(usage_callback.usage_metadata)
    if summary["total_tokens"]:
        await emitter.emit({"type": "usage", "data": summary})
        await record_usage(db, org_id=org.org_id, run_id=run.id, summary=summary)

    await _finalize_run(db, graph, config, run, interrupted=result["interrupted"])
    await db.commit()
    return LaunchResult(run=run, interrupted=result["interrupted"], last_seq=result["last_seq"])


async def _load_run_status(org_id: UUID, run_id: UUID) -> str | None:
    """Read a run's current status on a short-lived session (the durable cancel poll).

    Deliberately not the run's own session: that session is inside the graph's transaction,
    and issuing a query on it mid-run could interleave with pending writes.
    """
    async with AsyncSessionLocal() as poll_db:
        await poll_db.execute(
            text("SELECT set_config('app.current_org', :org, false)"), {"org": str(org_id)}
        )
        run = await OrgScopedRepository(poll_db, Run, org_id).get(run_id)
        return run.status if run is not None else None


async def _finalize_run(
    db: AsyncSession, graph: Any, config: Mapping[str, Any], run: Run, *, interrupted: bool
) -> None:
    """Update the run row from the final blackboard and persist the artifact."""
    snapshot = await graph.aget_state(config)
    values: Mapping[str, Any] = snapshot.values or {}

    run.rounds = int(values.get("round", 0) or 0)
    run.converged = bool(values.get("converged", False))
    if interrupted:
        run.status = "paused"  # awaiting POST /sessions/{id}/resume
        return

    run.status = "completed"
    run.finished_at = datetime.now(UTC)
    artifact = _build_artifact(values)
    db.add(
        Artifact(
            org_id=run.org_id,
            run_id=run.id,
            kind=artifact["kind"],
            content=artifact["content"],
            content_format=artifact["content_format"],
        )
    )


def _build_artifact(values: Mapping[str, Any]) -> dict[str, Any]:
    """Build the artifact record from final state (mirrors end_node, TECHNICAL §11.4)."""
    decision = values.get("hitl_decision")
    if isinstance(decision, Mapping) and decision.get("type") == "reject":
        reason = decision.get("reason")
        return {
            "kind": "rejected",
            "content": reason or "Run rejected by the human reviewer; no output synthesised.",
            "content_format": "markdown",
        }
    return {
        "kind": "synthesis",
        "content": values.get("final_output"),
        "content_format": "markdown",
    }
