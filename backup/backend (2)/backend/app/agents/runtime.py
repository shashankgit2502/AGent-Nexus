"""Agent turn execution — invoke an agent and map its output (ARCH §22.2 output).

This is what a single peer agent *does* in a round: render the current blackboard
into a message, run the (real) ReAct loop, and translate the typed
:class:`ContributionOut` back into the additive blackboard channels
(``contributions`` / ``critiques`` / ``events``) the graph reducers merge (§6).

Step boundary: the parallel ``Send()`` fan-out node calls this once per agent in
Step 5 (with the idempotency key of §22.5). Here in Step 4 it is exercised
directly so we can prove "one real agent runs a turn → contribution + confidence"
(the Step-4 acceptance check) without yet touching the graph wiring.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.a2a.limits import DEFAULT_LIMITS, A2ALimits
from app.a2a.messages import A2AMessage, normalize_messages
from app.agents.config import AgentConfig
from app.agents.contribution import ContributionOut
from app.agents.prompts import render_round_message
from app.graph.context import EmitFn
from app.graph.state import (
    Contribution,
    Critique,
    current_run_id,
    make_event,
    previous_round_contributions,
    text_block,
)

logger = logging.getLogger(__name__)

# A salvage attempt for a turn that ended without the structured exit tool: given
# the finished turn's messages, coax a ``ContributionOut`` from the same model.
# Returns ``None`` if it cannot — the caller then abstains (§21.5).
RepairFn = Callable[[list[BaseMessage]], "ContributionOut | None"]

_REPAIR_INSTRUCTION = (
    "You ended your turn without calling the required `ContributionOut` tool. "
    "Using your reasoning and any tool results above, produce that structured "
    "contribution now: content (your proposal for this round), confidence (your "
    "honest 0.0-1.0 self-assessment), responds_to, and any critiques."
)


def make_structured_repair(model: BaseChatModel) -> RepairFn:
    """Build a one-shot structured-output salvage (root-cause fix, R3).

    Failure mode this addresses: some (weaker) tool-calling models finish a ReAct
    turn with a plain-text answer and never invoke the ``ContributionOut`` exit
    tool, so ``structured_response`` is ``None`` and the whole turn is discarded as
    a confidence-0 abstention — even though the model produced real work.
    ``ToolStrategy.handle_errors`` does **not** cover this (it only retries bad
    args / multiple tool calls; verified against the LangChain v1 docs), so we add
    it here.

    Rather than fabricate a confidence the model never reported, we re-ask the
    *same* model in a single focused call with no competing work tools to convert
    its own answer into the typed schema (its genuine self-reported confidence
    included). If even that fails, we return ``None`` and the caller abstains.
    """
    extractor = model.with_structured_output(ContributionOut)

    def repair(messages: list[BaseMessage]) -> ContributionOut | None:
        try:
            result = extractor.invoke([*messages, HumanMessage(content=_REPAIR_INSTRUCTION)])
        except Exception:  # noqa: BLE001 — fallback path; any failure → graceful abstention.
            logger.exception("structured-output repair call failed")
            return None
        return result if isinstance(result, ContributionOut) else None

    return repair


class AgentTurnError(RuntimeError):
    """An agent turn did not produce the required structured contribution.

    Raised (rather than swallowed, R3) when ``structured_response`` is missing or
    the wrong type — the mesh node (Step 5) turns this into a graceful abstention
    per §21.5, but the failure is never silently hidden here.
    """


# The ToolStrategy structured-output tool is named after the response schema. It
# is the agent's *exit* mechanism, not a tool the agent used to do work, so it must
# not appear in the transparency `tool_calls` (§6) — otherwise the AG-UI would
# render a phantom tool call.
_RESPONSE_FORMAT_TOOL = ContributionOut.__name__


def _extract_tool_calls(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """Collect the agent's *work* tool calls for transparency / AG-UI rendering (§6).

    Excludes the structured-output sentinel (`ContributionOut`); see note above.
    """
    calls: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls or []:
                if tool_call["name"] == _RESPONSE_FORMAT_TOOL:
                    continue
                calls.append({"name": tool_call["name"], "args": tool_call.get("args", {})})
    return calls


def _reasoning_texts(message: AIMessage) -> list[str]:
    """Pull an AI message's reasoning / narration out of its standard content blocks.

    Reads ``content_blocks`` (langchain-core's provider-normalised view, verified on
    langchain-core 1.4.7) rather than the raw ``content`` so this is stable across
    providers whose native shapes differ. Both explicit ``reasoning`` blocks and
    plain ``text`` narration count as the agent "thinking out loud"; the agent's
    *answer* travels separately as ``structured_response`` → the ``contribution``
    event, so this never double-emits the proposal.
    """
    texts: list[str] = []
    for block in getattr(message, "content_blocks", None) or []:
        btype = block.get("type")
        if btype == "reasoning":
            text = (block.get("reasoning") or block.get("text") or "").strip()
        elif btype == "text":
            text = (block.get("text") or "").strip()
        else:
            continue
        if text:
            texts.append(text)
    return texts


def turn_events(
    messages: list[BaseMessage], *, agent_id: str, current_round: int
) -> list[dict[str, Any]]:
    """Project one agent's ReAct trajectory into ordered AG-UI events (ARCH §24.4).

    Round-cadenced and event-derived (CLAUDE.md §3 locked decision): the events are
    read **post-hoc** from the completed turn's messages, in trajectory order —
    each ``reasoning`` delta, each work ``tool_call``, then each ``tool_result`` —
    not a per-token live stream. The ``ContributionOut`` structured-output tool is
    the agent's *exit* mechanism, not work, so it is filtered from both ``tool_call``
    and ``tool_result`` (same rule as :func:`_extract_tool_calls`, §6).

    Shared by the mesh ``agent_turn`` and the no-team chat stream
    (:mod:`app.chat.noteam_stream`) so both surfaces project trajectories identically.
    """
    events: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, AIMessage):
            for text in _reasoning_texts(message):
                events.append(
                    make_event("reasoning", agent_id=agent_id, round=current_round, text=text)
                )
            for tool_call in message.tool_calls or []:
                if tool_call["name"] == _RESPONSE_FORMAT_TOOL:
                    continue
                events.append(
                    make_event(
                        "tool_call",
                        agent_id=agent_id,
                        round=current_round,
                        tool=tool_call["name"],
                        args=tool_call.get("args", {}),
                    )
                )
        elif isinstance(message, ToolMessage):
            if message.name == _RESPONSE_FORMAT_TOOL:
                continue
            events.append(
                make_event(
                    "tool_result",
                    agent_id=agent_id,
                    round=current_round,
                    tool=message.name or "",
                    result=message.content,
                )
            )
    return events


def _message_events(messages: list[A2AMessage]) -> list[dict[str, Any]]:
    """Project validated A2A messages into AG-UI ``a2a_message`` events (§24.4).

    Emitted so the Workspace can draw *who asked whom for what* as real, event-derived
    edges. Only messages that survived validation are emitted — the UI must never show a
    hand-off that was actually dropped.
    """
    return [
        make_event(
            "a2a_message",
            id=m["id"],
            sender=m["sender"],
            recipients=m["recipients"],
            intent=m["intent"],
            round=m["round"],
            payload=m["payload"],
            in_reply_to=m.get("in_reply_to"),
        )
        for m in messages
    ]


def _map_messages(
    structured: ContributionOut,
    *,
    agent_id: str,
    current_round: int,
    blackboard: Mapping[str, Any],
    limits: A2ALimits,
) -> tuple[list[A2AMessage], list[dict[str, Any]]]:
    """Validate the turn's proposed messages onto the blackboard (§23.4 → §23.5).

    The model's ``MessageOut`` list crosses a trust boundary, so it is projected to the
    carrier-agnostic dict form and handed to :func:`normalize_messages`, which enforces
    every §23.5 rule (roster, self-target, one-vote, dedup, delegation depth, budget).

    ``visible_peers`` is the same set the round prompt actually showed this agent — peers
    that contributed in the previous round. Passing it is what makes "you may only endorse
    or critique work you were shown" enforceable rather than advisory: a vote for a
    contribution the agent never saw cannot be an informed vote.

    Warnings are logged, not raised: a dropped message is a degraded turn, never a failed
    one — one malformed hand-off must not cost the round an entire contribution (§21.5).
    """
    if not structured.messages:
        return [], []

    visible = sorted({c["agent_id"] for c in previous_round_contributions(blackboard)})
    messages, warnings = normalize_messages(
        [m.to_proposed() for m in structured.messages],
        sender=agent_id,
        current_round=current_round,
        run_id=current_run_id(blackboard),
        roster=[str(a) for a in (blackboard.get("active_agent_ids") or [])],
        visible_peers=visible,
        existing=list(blackboard.get("messages") or []),
        budget=limits.max_messages_per_turn,
        max_delegation_depth=limits.max_delegation_depth,
    )
    for warning in warnings:
        logger.info("a2a message dropped: %s", warning)
    return messages, _message_events(messages)


def usage_from_messages(messages: list[BaseMessage]) -> dict[str, int] | None:
    """Sum this turn's own token usage from its ``AIMessage``s (ARCH §21.7).

    This is the **per-agent** view. It is read from the turn's messages rather than from a
    second callback handler on purpose: a child config's ``callbacks`` list *replaces* the
    inherited handlers instead of extending them, so attaching a per-turn handler would
    silently zero the run-level total that the whole metering depends on.

    Returns ``None`` when no message reported usage — a provider that omits
    ``usage_metadata`` yields no number, and showing 0 would misreport "free" rather than
    "unknown".
    """
    prompt = completion = 0
    seen = False
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        usage = getattr(message, "usage_metadata", None)
        if not usage:
            continue
        seen = True
        prompt += int(usage.get("input_tokens") or 0)
        completion += int(usage.get("output_tokens") or 0)
    if not seen:
        return None
    return {"input": prompt, "output": completion, "total": prompt + completion}


def _valid_responds_to(
    claimed: list[str], *, blackboard: Mapping[str, Any], self_id: str
) -> list[str]:
    """Keep only honest reply targets: peers whose prior-round work the agent saw.

    The model declares ``responds_to`` freely, so we validate it (R5): a target is
    kept only if it is a *different* agent that actually contributed in the
    previous round (the exact set ``render_round_message`` showed this agent). This
    prevents a hallucinated or self-referential id from producing a phantom reply
    edge in the AG-UI. Order-preserving + de-duplicated.
    """
    visible = {c["agent_id"] for c in previous_round_contributions(blackboard)}
    seen: set[str] = set()
    kept: list[str] = []
    for target in claimed:
        if target != self_id and target in visible and target not in seen:
            seen.add(target)
            kept.append(target)
    return kept


def _to_blackboard_update(
    result: Mapping[str, Any],
    *,
    cfg: AgentConfig,
    current_round: int,
    blackboard: Mapping[str, Any],
    repair: RepairFn | None = None,
    live_activity: bool = False,
    limits: A2ALimits = DEFAULT_LIMITS,
) -> dict[str, Any]:
    """Map an agent invocation result to an additive ``CollabState`` update (§22.2).

    If the turn ended without a ``ContributionOut`` (the model answered in plain
    text instead of calling the exit tool) and a ``repair`` is supplied, attempt a
    one-shot structured-output salvage before giving up (§21.5 / R3). Only if that
    also fails do we raise :class:`AgentTurnError` for the node to record as an
    abstention.
    """
    agent_id = str(cfg.id)
    messages = list(result.get("messages", []))
    structured = result.get("structured_response")
    if not isinstance(structured, ContributionOut):
        repaired = repair(messages) if repair is not None else None
        if isinstance(repaired, ContributionOut):
            logger.info(
                "agent %s did not call ContributionOut; recovered via structured-output repair",
                cfg.id,
            )
            structured = repaired
        else:
            raise AgentTurnError(
                f"agent {cfg.id} returned no ContributionOut structured_response "
                f"(got {type(structured).__name__}); cannot score this turn"
            )
    responds_to = _valid_responds_to(
        list(structured.responds_to), blackboard=blackboard, self_id=agent_id
    )
    # Stamp this run onto everything written to the blackboard (ARCH §22.5): a thread
    # hosts many runs and `round` restarts each time, so `run_id` is what keeps this
    # run's work distinguishable from the previous run's on the same thread.
    run_id = current_run_id(blackboard)
    contribution: Contribution = {
        "agent_id": agent_id,
        "round": current_round,
        "run_id": run_id,
        "content": structured.content,
        "confidence": structured.confidence,
        "tool_calls": _extract_tool_calls(messages),
        "responds_to": responds_to,
    }
    critiques: list[Critique] = [
        {
            "from_agent": agent_id,
            "target_agent": c.target_agent,
            "round": current_round,
            "run_id": run_id,
            "content": c.content,
            "severity": c.severity,
        }
        for c in structured.critiques
    ]
    # Ordered AG-UI projection of the turn (ARCH §24.4): the agent's reasoning /
    # tool calls / tool results (in trajectory order), then its ``contribution``
    # carrying the proposal as a §24.6 content block, then one ``critique`` per peer
    # critique. ``agent_turn_start`` is prepended by ``agent_turn_node`` (covers the
    # stub/abstention paths too), so it is not added here.
    #
    # ``live_activity``: when the caller already streamed the reasoning/tool events
    # **live** (Bug 5 — :func:`stream_agent_events`), they must not be re-emitted
    # here, so only the round-cadenced ``contribution`` + ``critique`` remain.
    activity = (
        []
        if live_activity
        else turn_events(messages, agent_id=agent_id, current_round=current_round)
    )
    a2a_messages, a2a_events = _map_messages(
        structured,
        agent_id=agent_id,
        current_round=current_round,
        blackboard=blackboard,
        limits=limits,
    )
    events = [
        *activity,
        make_event(
            "contribution",
            agent_id=agent_id,
            round=current_round,
            confidence=structured.confidence,
            content_blocks=[text_block(structured.content)],
            responds_to=responds_to,
            # Per-agent token cost of this turn (§21.7). Omitted entirely when the provider
            # reported no usage, so the UI can distinguish "unknown" from "zero".
            **({"tokens": turn_usage} if (turn_usage := usage_from_messages(messages)) else {}),
        ),
        *(
            make_event(
                "critique",
                sender=agent_id,
                target=c.target_agent,
                round=current_round,
                severity=c.severity,
                content=c.content,
            )
            for c in structured.critiques
        ),
        *a2a_events,
    ]
    return {
        "contributions": [contribution],
        "critiques": critiques,
        # Only present when the agent actually sent something, so a turn with no messages
        # writes nothing to the channel (an empty list would be a harmless but noisy write).
        **({"messages": a2a_messages} if a2a_messages else {}),
        "events": events,
    }


def run_agent_turn(
    agent: CompiledStateGraph[Any, Any, Any, Any],
    cfg: AgentConfig,
    blackboard: Mapping[str, Any],
    *,
    repair: RepairFn | None = None,
    limits: A2ALimits = DEFAULT_LIMITS,
) -> dict[str, Any]:
    """Run one agent's round synchronously and return the blackboard update.

    ``repair`` (optional) salvages a turn that ended without the structured exit
    tool; see :func:`make_structured_repair`.
    """
    current_round = int(blackboard.get("round", 1))
    message = render_round_message(cfg, blackboard, limits=limits)
    result = agent.invoke({"messages": [HumanMessage(content=message)]})
    return _to_blackboard_update(
        result,
        cfg=cfg,
        current_round=current_round,
        blackboard=blackboard,
        repair=repair,
        limits=limits,
    )


async def arun_agent_turn(
    agent: CompiledStateGraph[Any, Any, Any, Any],
    cfg: AgentConfig,
    blackboard: Mapping[str, Any],
    *,
    repair: RepairFn | None = None,
    limits: A2ALimits = DEFAULT_LIMITS,
) -> dict[str, Any]:
    """Run one agent's round asynchronously (R5: async clients in the mesh)."""
    current_round = int(blackboard.get("round", 1))
    message = render_round_message(cfg, blackboard, limits=limits)
    result = await agent.ainvoke({"messages": [HumanMessage(content=message)]})
    return _to_blackboard_update(
        result,
        cfg=cfg,
        current_round=current_round,
        blackboard=blackboard,
        repair=repair,
        limits=limits,
    )


def _tool_result_content(output: Any) -> Any:
    """The renderable payload of a tool result (a ``ToolMessage`` carries ``.content``).

    deepagents' state tools (``write_todos``, memory edits) return a LangGraph
    ``Command`` whose ``update`` carries the state delta plus the ``ToolMessage``
    the tool node will append. The renderable part is that message's content — the
    raw ``Command`` is a Python object the AG-UI cannot render (and, before the
    ``json_safe`` boundary existed, its JSONB insert failure killed the live stream
    — the RCA'd root cause of runs stalling on "thinking").
    """
    if isinstance(output, ToolMessage):
        return output.content
    if isinstance(output, Command):
        update = output.update if isinstance(output.update, Mapping) else {}
        for message in reversed(list(update.get("messages") or [])):
            if isinstance(message, ToolMessage):
                return message.content
        keys = ", ".join(sorted(str(k) for k in update)) or "state"
        return f"[updated: {keys}]"
    return output


async def stream_agent_events(
    agent: CompiledStateGraph[Any, Any, Any, Any],
    inputs: Mapping[str, Any],
    *,
    agent_id: str,
    current_round: int,
    emit: EmitFn,
    config: RunnableConfig | None = None,
) -> Mapping[str, Any]:
    """Stream one agent's ReAct trajectory, emitting activity events LIVE (Bug 5).

    Drives ``agent.astream_events(version="v2")`` (R1-verified against langchain-core
    1.4.7) and emits, as they happen — not post-hoc — each ``reasoning`` (from an
    ``on_chat_model_end`` message's content blocks), each work ``tool_call``
    (``on_tool_start``), and each ``tool_result`` (``on_tool_end``). The
    ``ContributionOut`` exit tool is the agent's structured-output mechanism (handled
    by middleware, not executed as a tool) so it never surfaces as a tool event; we
    still guard against it by name (§6). Returns the agent's final result mapping (the
    last ``on_chain_end`` whose output is the agent **state** — a mapping with
    ``messages``; the root chain completes last). We match by shape, **not**
    ``parent_ids``: when this agent runs *inside* a graph node the inner run inherits
    the outer run as its parent, so ``parent_ids`` is never empty — relying on it made
    the post-hoc structured-output repair fire on every live turn (R3).

    Emit isolation (R3): the events are *visibility*, the turn is the work. A failure
    while persisting/publishing ONE event (e.g. a payload the store rejects, a
    transient DB error) must cost that one event — logged loudly — not the stream:
    before this isolation, a single bad emit aborted the stream mid-turn and the
    fallback re-ran the ENTIRE turn non-streaming, doubling LLM latency and blowing
    the turn-timeout budget (the RCA'd cause of round-wide 600s abstentions).
    """

    async def safe_emit(raw: Mapping[str, Any]) -> None:
        try:
            await emit(raw)
        except Exception:  # noqa: BLE001 — visibility only; the turn must not die for one event.
            logger.exception(
                "live emit failed for agent %s (event type=%s); event dropped, turn continues",
                agent_id,
                raw.get("type"),
            )

    result: Mapping[str, Any] = {}
    async for event in agent.astream_events(dict(inputs), config, version="v2"):
        etype = event["event"]
        data = event.get("data") or {}
        name = event.get("name") or ""
        if etype == "on_tool_start" and name != _RESPONSE_FORMAT_TOOL:
            tool_input = data.get("input")
            await safe_emit(
                make_event(
                    "tool_call",
                    agent_id=agent_id,
                    round=current_round,
                    tool=name,
                    args=tool_input if isinstance(tool_input, dict) else {},
                )
            )
        elif etype == "on_tool_end" and name != _RESPONSE_FORMAT_TOOL:
            await safe_emit(
                make_event(
                    "tool_result",
                    agent_id=agent_id,
                    round=current_round,
                    tool=name,
                    result=_tool_result_content(data.get("output")),
                )
            )
        elif etype == "on_chat_model_end":
            output = data.get("output")
            if isinstance(output, AIMessage):
                for text in _reasoning_texts(output):
                    await safe_emit(
                        make_event(
                            "reasoning", agent_id=agent_id, round=current_round, text=text
                        )
                    )
        elif etype == "on_chain_end":
            # The agent's final state is the last on_chain_end whose output is the
            # state mapping (carries ``messages``; for the mesh also
            # ``structured_response``). Matched by shape so it works whether or not the
            # agent runs nested inside an outer graph node (see docstring).
            candidate = data.get("output")
            if isinstance(candidate, Mapping) and "messages" in candidate:
                result = candidate
    return result


async def astream_agent_turn(
    agent: CompiledStateGraph[Any, Any, Any, Any],
    cfg: AgentConfig,
    blackboard: Mapping[str, Any],
    *,
    emit: EmitFn,
    repair: RepairFn | None = None,
    limits: A2ALimits = DEFAULT_LIMITS,
) -> dict[str, Any]:
    """One mesh turn with **live** activity streaming, falling back if streaming fails.

    Streams the agent (emitting reasoning/tool events live via ``emit``) and maps the
    final result onto the blackboard with ``live_activity=True`` so those events are
    not re-emitted in the returned update — only the round-cadenced ``contribution`` /
    ``critique`` are, which keep the debate thread + edge animation round-cadenced.

    Resilience (Bug 1, R3): live streaming is **best-effort visibility**, never a new
    failure mode. ``astream_events`` enforces ``langchain_openai``'s per-chunk timeout
    (``StreamChunkTimeoutError``), which a slow / non-streaming model (e.g. a reasoning
    model that emits no chunk for 120s) trips even though a plain ``ainvoke`` would
    succeed. So if streaming raises, we log and fall back to non-streaming ``ainvoke``
    — the turn still completes (it just has no live activity events for that turn,
    projected post-hoc via ``live_activity=False``) instead of abstaining.
    """
    current_round = int(blackboard.get("round", 1))
    message = render_round_message(cfg, blackboard, limits=limits)
    inputs = {"messages": [HumanMessage(content=message)]}
    try:
        result = await stream_agent_events(
            agent, inputs, agent_id=str(cfg.id), current_round=current_round, emit=emit
        )
        live = True
    except Exception as exc:  # noqa: BLE001 — streaming is best-effort; the turn must still finish.
        logger.warning(
            "live streaming failed for agent %s (%s: %s); falling back to non-streaming ainvoke",
            cfg.id,
            type(exc).__name__,
            exc,
        )
        result = await agent.ainvoke(inputs)
        live = False
    return _to_blackboard_update(
        result,
        cfg=cfg,
        current_round=current_round,
        blackboard=blackboard,
        repair=repair,
        live_activity=live,
        limits=limits,
    )
