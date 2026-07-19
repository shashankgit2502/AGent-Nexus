"""No-team single-LLM chat streaming (ARCH §8.5.4).

A no-team turn runs **one** ``create_agent`` (no mesh, no consensus — the §3 locked
constraint) but, like every other run, executes in the background and emits its
trajectory as the AG-UI event stream so the client renders it live (§8.5.4: no-team
emits ``text``/``reasoning``/``tool_call`` events). It is given a lightweight ``run``
purely as the stream-correlation key (§24.3 envelopes are run-keyed); the §8.5.2
"without a run" phrasing is superseded here by the §24 streaming contract.

Emission is **round-cadenced and event-derived**, not per-token — identical to the
mesh (CLAUDE.md §3): the agent runs to completion, then its reasoning / tool calls
are projected post-hoc via the shared :func:`app.agents.runtime.turn_events`, so
there is exactly one projection path for both surfaces (R2, no reinvention).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy import text as sql_text

from app.agents.runtime import turn_events
from app.chat.single_agent import run_noteam_agent
from app.core.config import get_settings
from app.core.identity import OrgContext
from app.db.models import Artifact, Message, Run
from app.db.repositories import OrgScopedRepository
from app.db.session import AsyncSessionLocal
from app.graph.state import make_event, text_block
from app.streaming.emitter import RunEventEmitter
from app.streaming.run_service import fail_run

logger = logging.getLogger(__name__)

# Synthetic single-agent label for the no-team roster (no team agents to join).
_AGENT_LABEL = "assistant"


async def stream_noteam_turn(
    *,
    app: FastAPI,
    org: OrgContext,
    run_id: UUID,
    conversation_id: UUID,
    thread_id: str,
    model_ref: dict[str, Any] | None,
    user_text: str,
    assistant_id: UUID,
) -> None:
    """Drive one no-team turn on its own RLS-scoped session, emitting AG-UI events.

    Mirrors the mesh background executor's lifecycle (own session + GUC, error →
    ``failed`` + ``error`` event) but drives a single agent instead of the graph.
    """
    async with AsyncSessionLocal() as db:
        await db.execute(
            sql_text("SELECT set_config('app.current_org', :org, false)"),
            {"org": str(org.org_id)},
        )
        try:
            emitter = await RunEventEmitter.for_run(
                session_id=str(conversation_id),
                run_id=str(run_id),
                store=app.state.event_store,
                publisher=app.state.event_publisher,
            )
            await emitter.emit(make_event("run_start", goal=user_text, roster=[_AGENT_LABEL]))
            await emitter.emit(make_event("round_start", round=1))
            await emitter.emit(make_event("agent_turn_start", agent_id=_AGENT_LABEL, round=1))

            reply, messages = await run_noteam_agent(
                db,
                org_id=org.org_id,
                model_ref=model_ref,
                thread_id=thread_id,
                user_text=user_text,
                checkpointer=app.state.checkpointer,
                settings=get_settings(),
                conversation_id=conversation_id,
                # Live activity streaming (Bug 5): the agent's reasoning / tool calls
                # are emitted through here as they happen — so a no-team chat shows what
                # the assistant is doing instead of just "thinking" until it finishes.
                emit=emitter.emit,
                agent_label=_AGENT_LABEL,
            )

            # Fallback only: when the agent was NOT streamed live (stub path), it
            # returns its trajectory for post-hoc projection. The live path returns an
            # empty trajectory (events already emitted), so this is then a no-op.
            for event in turn_events(messages, agent_id=_AGENT_LABEL, current_round=1):
                await emitter.emit(event)
            # The answer travels as a contribution's content blocks (§24.6).
            await emitter.emit(
                make_event(
                    "contribution",
                    agent_id=_AGENT_LABEL,
                    round=1,
                    confidence=1.0,
                    content_blocks=[text_block(reply)],
                )
            )

            await _finalize(db, org=org, run_id=run_id, assistant_id=assistant_id, reply=reply)
            await db.commit()
            await emitter.emit(
                make_event(
                    "run_finished",
                    artifact={"kind": "synthesis", "content": reply, "content_format": "markdown"},
                )
            )
        except Exception:
            logger.exception("no-team run %s failed", run_id)
            await fail_run(app, db, org=org, run_id=run_id, stream_id=str(conversation_id))
        finally:
            try:
                await db.execute(sql_text("RESET app.current_org"))
                await db.commit()
            except Exception:
                logger.warning("failed to reset RLS GUC after no-team run", exc_info=True)


async def _finalize(
    db: Any, *, org: OrgContext, run_id: UUID, assistant_id: UUID, reply: str
) -> None:
    """Complete the run, persist its artifact, and fill the pending assistant turn."""
    run = await OrgScopedRepository(db, Run, org.org_id).get(run_id)
    if run is not None:
        run.status = "completed"
        run.rounds = 1
        run.finished_at = datetime.now(UTC)
    db.add(
        Artifact(
            org_id=org.org_id,
            run_id=run_id,
            kind="synthesis",
            content=reply,
            content_format="markdown",
        )
    )
    message = await OrgScopedRepository(db, Message, org.org_id).get(assistant_id)
    if message is not None:
        message.content = reply
    await db.flush()
