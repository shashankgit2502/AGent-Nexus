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
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.snapshot import build_mesh_context, load_active_agent_ids
from app.core.config import get_settings
from app.core.identity import OrgContext
from app.db.models import Artifact, Run
from app.db.models import Session as SessionModel
from app.db.repositories import OrgScopedRepository
from app.db.session import AsyncSessionLocal
from app.graph.build import build_collab_graph
from app.graph.state import initial_collab_state
from app.schemas.sessions import ResumeRequest, RunLaunch
from app.streaming.emitter import RunEventEmitter

logger = logging.getLogger(__name__)

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
        goal=payload.query,
        active_agent_ids=agent_ids,
        max_rounds=max_rounds,
        confidence_threshold=payload.confidence_threshold,
        hitl_enabled=deep,
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

    Shared by the mesh path (:func:`spawn_run`) and the no-team chat stream. Two
    invariants:

    * the run→org mapping is registered **synchronously**, before the task is
      scheduled — a WS client may connect (and replay) the instant the launch POST
      returns, *before* the task starts, so the RLS-scoped event store must already
      know this run's org (else ``replay`` raises ``RunOrgUnknown``);
    * the task is strongly referenced in ``app.state.run_tasks`` until it finishes
      (asyncio only weakly references tasks, so an untracked task can be GC'd
      mid-flight); the lifespan awaits any in-flight tasks on shutdown.
    """
    event_store = app.state.event_store
    if hasattr(event_store, "register_run"):
        event_store.register_run(str(run_id), org.org_id)

    tasks: set[asyncio.Task[None]] = app.state.run_tasks
    task = asyncio.create_task(coro)
    tasks.add(task)
    task.add_done_callback(tasks.discard)
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
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    from app.streaming.runner import stream_run  # local import avoids an import cycle

    result = await stream_run(
        graph, graph_input=graph_input, config=config, emitter=emitter, context=context
    )
    await _finalize_run(db, graph, config, run, interrupted=result["interrupted"])
    await db.commit()
    return LaunchResult(run=run, interrupted=result["interrupted"], last_seq=result["last_seq"])


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
