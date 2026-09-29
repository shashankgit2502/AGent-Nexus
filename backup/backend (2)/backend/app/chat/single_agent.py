"""No-team single-LLM chat (ARCH §8.5 — "one ``create_agent`` + checkpointer").

A no-team conversation is the simplest mode: a single ReAct agent on the
conversation's checkpointer thread, **no mesh, no consensus, no run** (ARCH §8.5.1).
Multi-turn context carries across turns through the checkpointer (verified via the
LangChain docs MCP: pass the new ``HumanMessage`` + a ``thread_id`` and the agent
resumes prior history — R1).

Both-paths policy (consistent with :mod:`app.agents.snapshot`)
-------------------------------------------------------------
If the conversation's ``model_ref`` resolves to a live model whose secret is
available, we run a real ``create_agent``. Otherwise we log *why* and fall back to a
deterministic **stub** reply, so a no-team conversation is exercisable end-to-end
without live provider keys (the Step-10 acceptance check, and dev). The failure is
logged, never silently swallowed (R3).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runtime import stream_agent_events
from app.agents.snapshot import build_conversation_attachment_tool, build_org_resolver
from app.core.config import Settings
from app.graph.context import EmitFn
from app.models_layer.resolver import AgentModelRef

logger = logging.getLogger(__name__)

# Prefix making the stub reply unmistakable in the UI/logs (no silent fakery).
_STUB_PREFIX = "[stub reply — no model configured]"

# System prompt added only when the conversation has uploaded files, so the single
# agent knows to read them via `search_uploaded_files` (Bug 2, ARCH §8.5.3).
_ATTACHMENTS_SYSTEM_PROMPT = (
    "The user has attached one or more files to this conversation. Use the "
    "`search_uploaded_files` tool to read them: call `search_uploaded_files(query)` "
    "to retrieve relevant passages and base your answer on the uploaded documents "
    "when the question refers to an attachment."
)


def _ref_from_model_ref(model_ref: Mapping[str, Any] | None) -> AgentModelRef:
    """Map a conversation's ``model_ref`` JSON to an :class:`AgentModelRef`.

    Expects ``profile_id`` (required) and optional ``model_id`` (the catalog model,
    used as the override). Raises ``KeyError``/``ValueError`` on a malformed ref —
    the caller treats that as "not viable" → stub path.
    """
    if not model_ref or "profile_id" not in model_ref:
        raise ValueError("no-team model_ref must include 'profile_id'")
    model_id = model_ref.get("model_id")
    return AgentModelRef(
        profile_id=UUID(str(model_ref["profile_id"])),
        override_model_id=UUID(str(model_id)) if model_id else None,
    )


async def run_noteam_agent(
    db: AsyncSession,
    *,
    org_id: UUID,
    model_ref: Mapping[str, Any] | None,
    thread_id: str,
    user_text: str,
    checkpointer: Any,
    settings: Settings,
    conversation_id: UUID | None = None,
    emit: EmitFn | None = None,
    agent_label: str = "assistant",
) -> tuple[str, list[BaseMessage]]:
    """Run one no-team turn and return ``(reply_text, trajectory_messages)`` (ARCH §8.5.2).

    Uses a real single ``create_agent`` when the model resolves; otherwise a
    deterministic stub (both-paths policy).

    Activity visibility (Bug 5): when ``emit`` is given, the agent's reasoning / tool
    calls are streamed **live** through it as they happen, and the returned trajectory
    is empty (already emitted) so the caller does not re-project them. Without ``emit``
    the agent is invoked normally and the trajectory messages are returned for the
    caller to project post-hoc (§8.5.4). The stub path returns an empty trajectory.

    When ``conversation_id`` is given and the conversation has ingested uploads, the
    agent additionally gets the ``search_uploaded_files`` tool so the user can ask
    about an attached document (Bug 2, §8.5.3). A no-team chat has no team, so the
    attachment's embedding model resolves to the org default (``team_id=None``).
    """
    try:
        resolver = await build_org_resolver(db, org_id=org_id, settings=settings)
        # No-team chat does not *require* tool-calling (no mesh gate, §9.3 relaxed)
        # but it may still BIND a tool — ``search_uploaded_files`` whenever the
        # conversation has an attachment, below. Those are two different questions:
        # the gate decides whether a model is eligible, ``expects_tools`` decides
        # which API surface it is built for. Conflating them meant a reasoning
        # model here was built for Chat Completions and then given tools, which
        # gpt-5.1+ refuse outright alongside a reasoning effort (400).
        model = resolver.resolve(
            _ref_from_model_ref(model_ref), require_tools=False, expects_tools=True
        )
        attach_tool = (
            await build_conversation_attachment_tool(
                db,
                org_id=org_id,
                team_id=None,
                conversation_id=conversation_id,
                settings=settings,
            )
            if conversation_id is not None
            else None
        )
        tools = [attach_tool] if attach_tool is not None else None
        system_prompt = _ATTACHMENTS_SYSTEM_PROMPT if attach_tool is not None else None
        agent = create_agent(
            model=model, tools=tools, system_prompt=system_prompt, checkpointer=checkpointer
        )
        human = HumanMessage(content=user_text)
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        if emit is not None:
            # Live path (Bug 5): stream the agent, emitting reasoning/tool events as
            # they occur; the empty trajectory tells the caller not to re-project.
            # Resilience (Bug 1): if streaming trips a model's per-chunk timeout, fall
            # back to non-streaming ainvoke below so the reply still arrives.
            try:
                result = await stream_agent_events(
                    agent,
                    {"messages": [human]},
                    agent_id=agent_label,
                    current_round=1,
                    emit=emit,
                    config=config,
                )
                return _last_ai_text(result), []
            except Exception as exc:  # noqa: BLE001 — streaming is best-effort; reply must arrive.
                logger.warning(
                    "no-team live streaming failed (%s: %s); falling back to ainvoke",
                    type(exc).__name__,
                    exc,
                )
        result = await agent.ainvoke({"messages": [human]}, config=config)
        messages = list(result.get("messages", []))
        return _last_ai_text(result), messages
    except Exception as exc:  # noqa: BLE001 — any wiring gap → deterministic stub (logged)
        reason = f"{type(exc).__name__}: {exc}"
        logger.warning("no-team real model not viable (%s); using stub reply", reason)
        # Surface *why* in the reply, not just a generic stub — otherwise a
        # misconfigured model fails invisibly (R3: no silent fakery). Local-dev
        # diagnostics; provider errors do not echo the API key.
        return f"{_STUB_PREFIX} ({reason}) received: {user_text}", []


def _last_ai_text(result: Mapping[str, Any]) -> str:
    """Extract the final assistant text from a ``create_agent`` result.

    Raises (not swallows, R3) if the agent returned no AI message — that is a real
    contract violation, distinct from the "no model configured" stub path above.
    """
    messages = list(result.get("messages", []))
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    raise RuntimeError("no-team agent returned no AIMessage")
