"""Chat turn orchestration (ARCH §8.5).

One user turn → one assistant reply, dispatched by conversation type:

* **Team chat** (``conversation.team_id`` set) spawns a **run-per-turn** on the
  conversation's thread, driving the *same* collaboration graph the Session
  Workspace uses (``drive_run``). ``deep_collaborate`` selects the full multi-round
  run; the default is the lightweight ``max_rounds=1`` pass (ARCH §8.5.1). The
  synthesized output becomes the assistant message (ARCH §8.5.2).
* **No-team chat** invokes a single ``create_agent`` directly on the thread — no run
  (ARCH §8.5.2; see :mod:`app.chat.single_agent`).

Locked-decision note (R6): team-chat turns run with **HITL off** in *both* modes —
``deep_collaborate`` controls ``max_rounds`` only. ARCH §8.5.1 lists deep-chat HITL
as *optional*, and §8.5.2 requires a turn to resolve to an assistant message in one
request (run-per-turn). The HITL-gated path remains the Session Workspace
(``/sessions``). This reuses one execution spine; it does not add an engine.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.snapshot import (
    load_active_agent_ids,
    load_agent_names,
    load_team_success_criteria,
)
from app.chat.noteam_stream import stream_noteam_turn
from app.core.config import get_settings
from app.core.identity import OrgContext
from app.db.models import Artifact, Attachment, Conversation, Message, Run
from app.db.repositories import OrgScopedRepository
from app.graph.state import initial_collab_state
from app.schemas.conversations import MessageCreate, SendMessageResponse
from app.streaming.run_service import LaunchResult, spawn_background, spawn_run

logger = logging.getLogger(__name__)

# Default rounds for a Deep Collaborate chat turn (ARCH §8 default τ/rounds).
_DEEP_MAX_ROUNDS = 3
_DEFAULT_TAU = 0.85

# The run's *prose* answer is the artifact `_finalize_run`/`end_node` build — kind
# "synthesis" (approved) or "rejected". Producer file deliverables (§2A) use file kinds
# (code/markdown/image/archive/…) and must NOT be mistaken for the chat answer.
_PROSE_ARTIFACT_KINDS = ("synthesis", "rejected")


async def send_message(
    *,
    app: FastAPI,
    db: AsyncSession,
    org: OrgContext,
    conversation: Conversation,
    payload: MessageCreate,
) -> SendMessageResponse:
    """Handle one user turn and return the assistant reply (ARCH §8.5.2)."""
    await _record_user_message(db, org=org, conversation=conversation, payload=payload)
    if conversation.team_id is None:
        return await _no_team_turn(
            app=app, db=db, org=org, conversation=conversation, payload=payload
        )
    return await _team_turn(app=app, db=db, org=org, conversation=conversation, payload=payload)


async def _record_user_message(
    db: AsyncSession, *, org: OrgContext, conversation: Conversation, payload: MessageCreate
) -> Message:
    """Persist the user's turn first so the transcript order is correct.

    Any ``attachment_ids`` the turn refers to are linked to this message (audit trail +
    future per-message scoping). Retrieval itself is conversation-scoped, so a missing
    or foreign id is ignored, not fatal (the upload already ingested independently).
    """
    message = await OrgScopedRepository(db, Message, org.org_id).add(
        Message(
            org_id=org.org_id,
            conversation_id=conversation.id,
            role="user",
            content=payload.content,
            deep_collaborate=payload.deep_collaborate,
        )
    )
    if payload.attachment_ids:
        await _link_attachments(
            db, org=org, conversation=conversation, message=message, ids=payload.attachment_ids
        )
    return message


async def _link_attachments(
    db: AsyncSession,
    *,
    org: OrgContext,
    conversation: Conversation,
    message: Message,
    ids: list[UUID],
) -> None:
    """Stamp ``message_id`` on this turn's attachments (only ones in this conversation)."""
    attachments = await OrgScopedRepository(db, Attachment, org.org_id).list(
        conversation_id=conversation.id
    )
    by_id = {a.id: a for a in attachments}
    for attachment_id in ids:
        attachment = by_id.get(attachment_id)
        if attachment is not None:
            attachment.message_id = message.id
    await db.flush()


async def _team_turn(
    *,
    app: FastAPI,
    db: AsyncSession,
    org: OrgContext,
    conversation: Conversation,
    payload: MessageCreate,
) -> SendMessageResponse:
    """Run-per-turn over the collab graph, executed in the background (ARCH §8.5.2/§24.5).

    The run streams live over ``WS /conversations/{id}/stream`` while it executes, so
    this returns immediately with the run + a **pending** assistant message (content
    ``None``). A post-completion hook fills that message from the synthesized
    artifact; the client reads the final text from the live ``run_finished`` event or
    by re-fetching the transcript (``GET /conversations/{id}/messages``).
    """
    assert conversation.team_id is not None  # guarded by the caller
    deep = payload.deep_collaborate
    max_rounds = _DEEP_MAX_ROUNDS if deep else 1
    # Same per-peer prompt compression budget the launched-session path uses (config.py)
    # so team-chat mesh runs stay under the provider rate limit too. 0 = unchanged.
    settings = get_settings()

    run = Run(
        org_id=org.org_id,
        conversation_id=conversation.id,  # XOR: a chat run has no session_id
        query=payload.content,
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.flush()
    # The assistant turn is created **pending** now (run-per-turn binding, transcript
    # order) and filled when the background run finishes.
    assistant = await OrgScopedRepository(db, Message, org.org_id).add(
        Message(
            org_id=org.org_id,
            conversation_id=conversation.id,
            role="assistant",
            content=None,
            run_id=run.id,
            deep_collaborate=deep,
        )
    )
    # Commit so the run + pending message are visible to the background task's own
    # session, the event store (FK for run_events), and any WS client connecting.
    await db.commit()

    agent_ids = await load_active_agent_ids(db, org_id=org.org_id, team_id=conversation.team_id)
    state = initial_collab_state(
        # Scope this turn's blackboard writes (ARCH §22.5). Chat is run-per-turn on ONE
        # conversation ``thread_id``, so this is the call site where the missing run scope
        # hurt most: every turn after the first collided with turn 1's (agent_id, round=1),
        # every agent was skipped by the idempotency guard, and the turn returned turn 1's
        # answer regardless of what was asked.
        run_id=str(run.id),
        goal=payload.content,
        active_agent_ids=agent_ids,
        # Same team configuration the Session Workspace path uses — a chat turn runs
        # the same graph, so it plans against the same criteria and names.
        success_criteria=await load_team_success_criteria(
            db, org_id=org.org_id, team_id=conversation.team_id
        ),
        agent_names=await load_agent_names(
            db, org_id=org.org_id, team_id=conversation.team_id
        ),
        max_rounds=max_rounds,
        confidence_threshold=_DEFAULT_TAU,
        hitl_enabled=False,  # chat turns never pause (see module docstring)
        peer_content_max_chars=settings.AGENT_PEER_CONTENT_MAX_CHARS,
    )

    assistant_id = assistant.id

    async def _fill_assistant(task_db: AsyncSession, result: LaunchResult) -> None:
        """Fill the pending assistant message from the run's synthesized artifact."""
        content = await _synthesized_content(task_db, org=org, run_id=result.run.id)
        message = await OrgScopedRepository(task_db, Message, org.org_id).get(assistant_id)
        if message is not None:
            message.content = content
            await task_db.flush()

    spawn_run(
        app=app,
        org=org,
        run_id=run.id,
        stream_id=str(conversation.id),
        team_id=conversation.team_id,
        thread_id=conversation.thread_id,
        graph_input=state,
        on_complete=_fill_assistant,
    )
    return SendMessageResponse.model_validate(
        {
            "assistant_message": assistant,
            "run": run,
            "stream_url": f"/conversations/{conversation.id}/stream?run_id={run.id}",
        }
    )


async def _no_team_turn(
    *,
    app: FastAPI,
    db: AsyncSession,
    org: OrgContext,
    conversation: Conversation,
    payload: MessageCreate,
) -> SendMessageResponse:
    """Single-agent reply, streamed live over a lightweight run (ARCH §8.5.4).

    No mesh / consensus (the §3 locked constraint) — but, like every run, it
    executes in the background and emits its trajectory (reasoning / tool_call /
    contribution) over ``WS /conversations/{id}/stream`` so the client renders it
    live. Returns immediately with the run + a pending assistant message (filled
    when the agent finishes).
    """
    run = Run(
        org_id=org.org_id,
        conversation_id=conversation.id,  # XOR: a chat run has no session_id
        query=payload.content,
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    await db.flush()
    assistant = await OrgScopedRepository(db, Message, org.org_id).add(
        Message(
            org_id=org.org_id,
            conversation_id=conversation.id,
            role="assistant",
            content=None,  # filled when the single-agent run finishes
            run_id=run.id,
            deep_collaborate=False,
        )
    )
    await db.commit()

    spawn_background(
        app,
        org=org,
        run_id=run.id,
        coro=stream_noteam_turn(
            app=app,
            org=org,
            run_id=run.id,
            conversation_id=conversation.id,
            thread_id=conversation.thread_id,
            model_ref=conversation.model_ref,
            user_text=payload.content,
            assistant_id=assistant.id,
        ),
    )
    return SendMessageResponse.model_validate(
        {
            "assistant_message": assistant,
            "run": run,
            "stream_url": f"/conversations/{conversation.id}/stream?run_id={run.id}",
        }
    )


async def _synthesized_content(db: AsyncSession, *, org: OrgContext, run_id: object) -> str | None:
    """Return the run's synthesized prose answer (the artifact ``_finalize_run`` writes).

    Scoped to the **prose** artifact (``kind in {synthesis, rejected}``) on purpose: the
    post-consensus artifact producer (ARTIFACTS §2A) writes *additional* file-deliverable
    rows to the same ``artifacts`` table — many with ``content`` NULL (binary bytes live in
    object storage, §7). An unscoped ``scalar`` could return one of those file rows, writing
    a NULL chat answer that leaves the turn stuck "pending" forever. The run's prose answer
    is always the single ``synthesis``/``rejected`` row; ``created_at desc`` is belt-and-
    suspenders against any future duplicate.
    """
    artifact = await db.scalar(
        select(Artifact)
        .where(
            Artifact.run_id == run_id,
            Artifact.org_id == org.org_id,
            Artifact.kind.in_(_PROSE_ARTIFACT_KINDS),
        )
        .order_by(Artifact.created_at.desc())
    )
    return artifact.content if artifact is not None else None
