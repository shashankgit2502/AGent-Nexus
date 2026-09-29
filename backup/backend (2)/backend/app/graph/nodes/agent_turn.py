"""Agent-turn node — one peer ReAct agent's round (ARCHITECTURE.md §4.2 / §22).

Fanned out with ``Send()`` and run **in parallel** for every active agent
(ARCH §7). Because many copies of this node execute in the same super-step, it
must write **only the additive channels** (`contributions`, `critiques`,
`events`) — never a scalar channel like `round` — or LangGraph raises an
``InvalidUpdateError`` on the concurrent scalar write.

Signature
---------
The node receives the raw ``Send`` payload (``{"agent_id": ..., **blackboard}``)
as ``payload`` and the graph's :class:`~app.graph.context.MeshContext` as
``runtime`` (LangGraph dependency injection, R1-verified against langgraph 1.2.5).
Reading ``agent_id`` from the payload is how each parallel instance knows which
agent it is; ``runtime.context.runner`` is how it runs that agent.

Two execution paths
-------------------
* **Real path** — a :class:`~app.graph.context.MeshRunner` is present in the
  runtime context: build + invoke the real ReAct agent (Step 4) and map its typed
  output onto the blackboard.
* **Stub path** — no runner (``runtime.context`` is ``None``, e.g. the foundation
  checkpoint/resume tests): return a deterministic stub contribution so the
  persistence and consensus loop can be exercised without an agent stack.

Resilience (ARCH §21.5): if a real turn raises (model error, malformed/missing
structured output), the node records a **confidence-0 abstention** and an `error`
event rather than letting one agent deadlock the round. This is architected
graceful degradation — the failure is logged with full context and surfaced as an
AG-UI `error` event, never silently swallowed (R3).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from langgraph.runtime import Runtime

from app.a2a.messages import A2AMessage, normalize_messages
from app.graph.context import MeshContext
from app.graph.state import (
    Contribution,
    Critique,
    current_run_id,
    in_run,
    make_event,
    text_block,
)
from app.models_layer.errors import ModelNotToolCapable

logger = logging.getLogger(__name__)

# Structured discriminator on the abstention `error` event (§24.4 `reason`), so the
# frontend can tell a *config/capability* abstention a user can fix (assign a
# tool-capable model) from a *transient* runtime failure, instead of string-matching
# the human message. Mirrored by the frontend ``ErrorReason`` union.
ABSTAIN_NOT_TOOL_CAPABLE = "not_tool_capable"
ABSTAIN_TIMEOUT = "timeout"
ABSTAIN_TURN_FAILED = "turn_failed"
# The run was stopped by the user before this agent's turn began (§21.6). Reuses the
# abstention shape rather than raising: the round still closes cleanly, and the UI shows
# *why* this agent produced nothing instead of leaving it pulsing "thinking" forever.
ABSTAIN_CANCELLED = "cancelled"


def _abstention_code(exc: BaseException) -> str:
    """Classify a turn failure into a stable ``reason`` code for the UI (§24.4)."""
    if isinstance(exc, ModelNotToolCapable):
        return ABSTAIN_NOT_TOOL_CAPABLE
    if isinstance(exc, asyncio.TimeoutError):
        return ABSTAIN_TIMEOUT
    return ABSTAIN_TURN_FAILED


# Round-ramped stub self-confidence (Bug 4). The opening round sits **below** the
# default τ (0.85, ARCH §8) so a Deep Collaborate run does not converge in round 1 —
# it debates a second round where peers can build on / critique each other, which is
# what drives the AG-UI reply + critique edges (§9.10) and the debate thread (§9.4).
# A later round is confident enough to converge. The lightweight 1-round chat is
# capped by ``max_rounds`` regardless, so it still resolves in a single pass.
STUB_OPENING_CONFIDENCE = 0.6
STUB_CONVERGED_CONFIDENCE = 0.9
# Back-compat alias (the prior single value); some tests reference it.
STUB_CONFIDENCE = STUB_CONVERGED_CONFIDENCE


def _stub_confidence(current_round: int) -> float:
    """Below τ on the opening round, converged thereafter (see module constants)."""
    return STUB_OPENING_CONFIDENCE if current_round <= 1 else STUB_CONVERGED_CONFIDENCE


def _prior_round_peers(payload: Mapping[str, Any], agent_id: str, current_round: int) -> list[str]:
    """Distinct peer agent-ids that contributed in the **previous** round (§23.4).

    The opening round has none (peers are produced in parallel this super-step and
    only become visible next round), so a round-1 stub builds on / critiques nobody —
    matching how a real agent behaves on the first round (no fabricated edges, §9.10).

    Run-scoped (§22.5) so a peer that contributed in a *previous run* on this thread is
    never presented as this run's prior-round peer.
    """
    if current_round <= 1:
        return []
    prior = current_round - 1
    run = current_run_id(payload)
    peers: list[str] = []
    for c in payload.get("contributions", []):
        other = c.get("agent_id")
        if c.get("round") == prior and other != agent_id and other not in peers and in_run(c, run):
            peers.append(other)
    return sorted(peers)


def _already_contributed(payload: Mapping[str, Any], agent_id: str, current_round: int) -> bool:
    """Idempotency guard keyed by ``(run_id, agent_id, round)`` (ARCH §22.5).

    Returns ``True`` if a contribution for this run+agent+round is already on the
    blackboard snapshot delivered to this turn.

    Scope (honest): LangGraph commits a node's update only on success, so an
    ordinary failure-then-retry never double-appends — that retry-safety is the
    framework's, not reimplemented here (R2). This guard additionally protects the
    pathological case of a *replayed* round whose contributions already persisted,
    matching §22.5's "check for an existing contribution before appending".

    Why ``run_id`` is part of the key (RCA — this was the defect):
    a checkpointer ``thread_id`` is per Session and per Conversation, and a thread hosts
    **many runs**, while the additive ``contributions`` channel persists across all of
    them and ``round`` restarts at 1 on every run. Keyed on ``(agent_id, round)`` alone,
    every agent on run 2 matched run 1's round-1 entry, this guard returned ``True``, the
    node returned ``{}`` before emitting anything, and consensus ranked run 1's stale
    contributions. Observable symptom: the second query on a session — and every chat
    turn after the first, since chat is run-per-turn on one conversation thread —
    silently returned the first run's answer for a completely different question.
    """
    run = current_run_id(payload)
    return any(
        c["agent_id"] == agent_id and c["round"] == current_round and in_run(c, run)
        for c in payload.get("contributions", [])
    )


def _stub_update(agent_id: str, current_round: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic stub turn (no runner configured) — a faithful multi-round debate.

    The stub emits the **same shape** a real agent does (ARCH §24.4): a round-cadenced
    ``reasoning`` narration, a ``contribution`` carrying ``responds_to`` (the prior-round
    peers it builds on → reply edges, §9.10), and one ``critique`` of a peer (→ critique
    edges). On the opening round there are no peers yet, so it emits only the
    contribution — never a fabricated edge. Every artifact is clearly ``[stub]``-marked
    so a keys-free run is unmistakable (R3 — no silent fakery); only the engine plumbing
    is exercised, not real reasoning.
    """
    content = f"[stub] {agent_id}'s proposal for round {current_round}"
    confidence = _stub_confidence(current_round)
    run = current_run_id(payload)
    contribution: Contribution = {
        "agent_id": agent_id,
        "round": current_round,
        "run_id": run,
        "content": content,
        "confidence": confidence,
        "tool_calls": [],
    }

    peers = _prior_round_peers(payload, agent_id, current_round)
    events: list[dict[str, Any]] = []
    critiques: list[Critique] = []
    messages: list[A2AMessage] = []
    if peers:
        # Building on / challenging the previous round's peers (round ≥ 2).
        contribution["responds_to"] = peers
        events.append(
            make_event(
                "reasoning",
                agent_id=agent_id,
                round=current_round,
                text=f"[stub] {agent_id} reviewing peers' round {current_round - 1} contributions",
            )
        )
        target = peers[0]
        critiques.append(
            {
                "from_agent": agent_id,
                "target_agent": target,
                "round": current_round,
                "run_id": run,
                "content": (
                    f"[stub] {agent_id} flags a concern with {target}'s "
                    f"round {current_round - 1} proposal"
                ),
                "severity": "major",
            }
        )
        # A2A signal (§23.3) — the stub must model a team that can actually *agree*,
        # not just object. It raises one concern AND backs the peer's direction, which
        # is what a converging team does: without the ENDORSE/VOTE its own critique
        # penalty (§8.1) would hold its score under τ forever, so a stub that only ever
        # critiques could never converge — it would model a permanently deadlocked team
        # and quietly turn the keys-free demo into a fixed max-rounds counter.
        # Emitted through the same validator as a real agent's, so the stub cannot
        # produce mail a real agent could not.
        messages, _ = normalize_messages(
            [
                {"intent": "ENDORSE", "payload": {"target_agent": target, "reason": "[stub] agrees"}},
                {"intent": "VOTE", "payload": {"target_agent": target}},
            ],
            sender=agent_id,
            current_round=current_round,
            run_id=run,
            roster=[str(a) for a in (payload.get("active_agent_ids") or [])],
            visible_peers=peers,
            existing=list(payload.get("messages") or []),
        )
        events.extend(
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
        )

    events.append(
        make_event(
            "contribution",
            agent_id=agent_id,
            round=current_round,
            confidence=confidence,
            content_blocks=[text_block(content)],
            responds_to=contribution.get("responds_to", []),
        )
    )
    events.extend(
        make_event(
            "critique",
            sender=c["from_agent"],
            target=c["target_agent"],
            round=c["round"],
            severity=c["severity"],
            content=c["content"],
        )
        for c in critiques
    )
    return {
        "contributions": [contribution],
        "critiques": critiques,
        **({"messages": messages} if messages else {}),
        "events": events,
    }


def _failure_reason(exc: Exception) -> str:
    """Human-readable failure reason for the abstention event + log (§21.5).

    Prefixes the exception type so the UI states *what kind* of failure occurred
    (e.g. ``PaymentRequiredResponseError: ...credits...`` or
    ``RemoteProtocolError: Server disconnected...``) instead of a bare message —
    this is what the AG-UI surfaces on the failed agent node so users can see why
    an agent dropped out rather than guessing. Falls back to the type name alone
    when the exception has no message.
    """
    detail = str(exc).strip()
    name = type(exc).__name__
    return f"{name}: {detail}" if detail else name


def _abstention_update(
    agent_id: str,
    current_round: int,
    reason: str,
    *,
    reason_code: str = ABSTAIN_TURN_FAILED,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Confidence-0 abstention so a failed agent doesn't stall the round (§21.5).

    ``reason`` is the human-readable message; ``reason_code`` is the stable §24.4
    discriminator (e.g. ``not_tool_capable``) the frontend maps to a distinct badge.
    ``run_id`` stamps the abstention into the current run (§22.5) so it is counted by
    this run's consensus — and only this run's.
    """
    contribution: Contribution = {
        "agent_id": agent_id,
        "round": current_round,
        "run_id": run_id,
        "content": f"[abstained] {agent_id} produced no contribution this round: {reason}",
        "confidence": 0.0,
        "tool_calls": [],
    }
    return {
        "contributions": [contribution],
        "events": [
            make_event(
                "error",
                scope="agent_turn",
                agent_id=agent_id,
                round=current_round,
                message=reason,
                reason=reason_code,
            )
        ],
    }


def agent_turn_node(payload: Mapping[str, Any], runtime: Runtime[MeshContext]) -> dict[str, Any]:
    """Produce one agent's contribution for the current round.

    Real agent when a :class:`MeshRunner` is injected; otherwise a stub. Failures
    degrade to a confidence-0 abstention (§21.5).
    """
    agent_id = str(payload["agent_id"])
    current_round = int(payload["round"])

    if _already_contributed(payload, agent_id, current_round):
        logger.debug(
            "agent_turn skipped (idempotent): agent=%s round=%s already present",
            agent_id,
            current_round,
        )
        return {}

    runner = runtime.context.runner if runtime.context is not None else None
    if runner is None:
        update = _stub_update(agent_id, current_round, payload)
    else:
        try:
            update = runner.run(agent_id, payload)
        except Exception as exc:  # noqa: BLE001 — §21.5 graceful degradation, see below.
            # Architected resilience, not error-swallowing (R3): the full error is
            # logged with a traceback and re-surfaced as an AG-UI `error` event; the
            # round still completes with this agent counted as an abstention.
            logger.exception(
                "agent_turn failed for agent=%s round=%s; recording abstention",
                agent_id,
                current_round,
            )
            update = _abstention_update(
                agent_id,
                current_round,
                reason=_failure_reason(exc),
                reason_code=_abstention_code(exc),
                run_id=current_run_id(payload),
            )

    # Bracket every path (real / stub / abstention) with an ``agent_turn_start``
    # marker so the UI can open this agent's turn before its reasoning/tool/
    # contribution events (ARCH §24.4). Emitted here (the node) rather than in the
    # runner so the stub and abstention paths get it too. The marker is prepended;
    # the within-turn order produced by the runner is preserved after it.
    turn_start = make_event("agent_turn_start", agent_id=agent_id, round=current_round)
    return {**update, "events": [turn_start, *update.get("events", [])]}


async def aagent_turn_node(
    payload: Mapping[str, Any], runtime: Runtime[MeshContext]
) -> dict[str, Any]:
    """Async agent turn (Bug 5), live-streaming gated by ``ctx.live_streaming``.

    Registered alongside :func:`agent_turn_node` via ``RunnableCallable`` so a sync
    ``invoke`` uses the post-hoc node and an async ``astream`` (the real run path) uses
    this one. With a ``runner`` + ``emit`` sink **and** ``ctx.live_streaming`` True,
    the agent's reasoning / tool_call / tool_result events are emitted live as they
    happen. When ``live_streaming`` is False (the default — token streaming corrupts
    tool-call names on some providers, see ``AGENT_LIVE_STREAMING``) the turn runs
    non-streaming and those events are projected post-hoc into the returned update
    (still round-cadenced). Either way ``agent_turn_start`` is emitted live so the UI
    shows the agent thinking the instant work starts. Without an ``emit`` (foundation
    tests, the stub path), it is byte-for-byte the post-hoc :func:`agent_turn_node`.
    """
    ctx = runtime.context
    runner = ctx.runner if ctx is not None else None
    emit = ctx.emit if ctx is not None else None
    if runner is None or emit is None:
        # No live sink → identical behaviour to the synchronous node (post-hoc events).
        return agent_turn_node(payload, runtime)

    agent_id = str(payload["agent_id"])
    current_round = int(payload["round"])
    if _already_contributed(payload, agent_id, current_round):
        return {}

    # Cancellation check BEFORE any model call (§21.6). The mesh dispatches every agent in
    # one super-step, so a stop that arrives mid-round would otherwise still pay for every
    # queued turn. Recorded as an abstention (not an exception) so the round closes cleanly.
    if ctx.should_cancel is not None and await ctx.should_cancel():
        return _abstention_update(
            agent_id,
            current_round,
            reason="run cancelled by the user before this turn started",
            reason_code=ABSTAIN_CANCELLED,
            run_id=current_run_id(payload),
        )

    # Open the turn live so the node shows "thinking" the instant work starts.
    await emit(make_event("agent_turn_start", agent_id=agent_id, round=current_round))
    try:
        # arun runs the turn (streaming live when ctx.live_streaming, else
        # non-streaming with post-hoc events in the returned update); either way the
        # run streamer emits the returned update, so nothing is double-emitted.
        #
        # Provider-agnostic per-turn timeout (R3/R4): a slow or unresponsive model — on
        # ANY provider — must degrade this *one* agent to an abstention rather than
        # stalling the whole round forever (§21.5). The bound's meaning depends on
        # what we can observe:
        #
        # * **Live streaming** — the turn emits reasoning/tool events as they happen,
        #   so "unresponsive" is measurable directly: the timeout bounds *inactivity*
        #   (time since the last emitted event), rescheduled forward on every emit.
        #   A model actively producing work is, by definition, responsive — cancelling
        #   it mid-output threw away real contributions and surfaced round-wide
        #   "no response within 600s" abstentions even though the backend logs showed
        #   the agents working (the RCA'd symptom).
        # * **Non-streaming** — nothing is observable until the turn returns, so the
        #   bound stays total wall-clock (``asyncio.wait_for``), as before.
        if ctx.turn_timeout_s is None:
            return await runner.arun(agent_id, payload, emit=emit, live=ctx.live_streaming)
        if not ctx.live_streaming:
            return await asyncio.wait_for(
                runner.arun(agent_id, payload, emit=emit, live=False),
                timeout=ctx.turn_timeout_s,
            )
        loop = asyncio.get_running_loop()
        timeout_s = ctx.turn_timeout_s
        async with asyncio.timeout(timeout_s) as watchdog:

            async def emit_and_extend(raw: Mapping[str, Any]) -> Any:
                result = await emit(raw)
                watchdog.reschedule(loop.time() + timeout_s)
                return result

            return await runner.arun(agent_id, payload, emit=emit_and_extend, live=True)
    except Exception as exc:  # noqa: BLE001 — §21.5 graceful degradation (TimeoutError included).
        reason = (
            f"no activity for {ctx.turn_timeout_s:.0f}s (model too slow/unresponsive)"
            if isinstance(exc, asyncio.TimeoutError) and ctx.turn_timeout_s is not None
            else _failure_reason(exc)
        )
        logger.warning(
            "agent_turn (live) for agent=%s round=%s ended in abstention: %s",
            agent_id,
            current_round,
            reason,
        )
        # agent_turn_start was already emitted live; the abstention's `error` event
        # rides the returned update (emitted by the run streamer). No double turn_start.
        return _abstention_update(
            agent_id,
            current_round,
            reason=reason,
            reason_code=_abstention_code(exc),
            run_id=current_run_id(payload),
        )
