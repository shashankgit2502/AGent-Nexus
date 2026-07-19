"""CollabState — the shared blackboard (ARCHITECTURE.md §6).

This `TypedDict` is the single shared structure every peer agent reads and writes
during a collaboration run. It is the *one* deliberately-custom component the
constitution allows (CLAUDE.md R2): the "blackboard" / mesh state. Everything
around it (graph runtime, checkpointer, agents) uses LangGraph/LangChain
primitives — only this domain state is hand-modelled.

Why the reducers are load-bearing
----------------------------------
`contributions`, `critiques`, and `events` are typed `Annotated[list[...], add]`.
During a mesh round the graph fans out to every active agent in parallel via
`Send()` (ARCH §7). Each agent returns an update to these channels at the *same*
super-step. The additive reducer (`operator.add`) tells LangGraph to MERGE those
concurrent writes by list concatenation instead of last-writer-wins clobbering.
Without it, parallel agents writing the same channel would race and silently
drop contributions.

Scalar channels (`round`, `converged`, `status`, `final_output`, ...) have **no**
reducer, so they must only ever be written by a node that runs *alone* in its
super-step (orchestrator, consensus, hitl, synthesizer, end_node). The parallel
`agent_turn` nodes deliberately write **only** the additive channels — see
`app/graph/nodes/agent_turn.py`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from operator import add
from typing import Annotated, Any, Literal, NotRequired, TypedDict

# A round's lifecycle phase. Mirrors the AG-UI run progression (ARCH §24.4).
RunStatus = Literal["init", "debating", "consensus", "hitl", "synth", "done"]


class Contribution(TypedDict):
    """One agent's proposal for one round (ARCH §6)."""

    agent_id: str
    round: int
    content: str
    confidence: float  # 0.0–1.0, self-reported (calibrated post-hoc later)
    tool_calls: list[dict[str, Any]]  # surfaced for transparency / AG-UI rendering
    # agent_ids of peers whose prior-round work this builds on (directed reply
    # correlation; drives the AG-UI reply edges, §9.10). NotRequired keeps older
    # constructors valid — readers default to an empty list.
    responds_to: NotRequired[list[str]]


class Critique(TypedDict):
    """A peer critique of another agent's contribution (ARCH §6 / A2A CRITIQUE)."""

    from_agent: str
    target_agent: str
    round: int
    content: str
    severity: Literal["minor", "major", "blocking"]


class HITLDecision(TypedDict):
    """A human's resolution of the HITL gate (ARCH §4.5).

    The gate offers three decisions on the converged candidate:

    * ``approve`` — accept the consensus result; the synthesizer merges it.
    * ``edit`` — replace the final output with the human's ``content`` verbatim
      (the human has authored the answer; the synthesizer does not overwrite it).
    * ``reject`` — discard the result; the synthesizer produces no output and the
      end node records a rejected artifact (``reason`` optional).

    ``source`` distinguishes a real human decision from the lightweight-path
    auto-approval (ARCH §8.5, ``hitl_enabled=False``).
    """

    type: Literal["approve", "edit", "reject"]
    content: NotRequired[str]  # edited final output (edit only)
    reason: NotRequired[str]  # rejection reason (reject only)
    source: NotRequired[Literal["human", "auto"]]


class CollabState(TypedDict):
    """The blackboard. Schema is locked by ARCHITECTURE.md §6.

    `hitl_enabled` is the single additive control flag beyond the §6 listing; it
    operationalises the "HITL off" lightweight path that ARCH §8.5 already
    defines as a parameter of this same graph (one execution spine). It is not a
    new engine or a reversal of a locked decision.
    """

    # ── Goal & framing (written by the Orchestrator entry node) ──────────────
    goal: str
    success_criteria: list[str]
    agent_task_framing: dict[str, str]  # agent_id -> tailored prompt

    # ── Mesh working memory (append-only, parallel-safe) ─────────────────────
    contributions: Annotated[list[Contribution], add]
    critiques: Annotated[list[Critique], add]

    # ── Consensus bookkeeping ────────────────────────────────────────────────
    round: int
    max_rounds: int
    confidence_threshold: float  # τ
    converged: bool
    consensus_ranking: list[str]  # "agent_id:round", best first

    # ── Lifecycle ────────────────────────────────────────────────────────────
    status: RunStatus
    active_agent_ids: list[str]  # dynamic per round (runtime spawn)
    final_output: str | None
    hitl_enabled: bool  # ARCH §8.5: full graph vs lightweight 1-round/no-HITL
    hitl_decision: HITLDecision | None  # set by the HITL gate; read by the synthesizer/end

    # ── AG-UI event stream (append-only projection) ──────────────────────────
    events: Annotated[list[dict[str, Any]], add]


def initial_collab_state(
    *,
    goal: str,
    active_agent_ids: Iterable[str],
    success_criteria: Iterable[str] | None = None,
    max_rounds: int = 3,
    confidence_threshold: float = 0.85,
    hitl_enabled: bool = False,
) -> CollabState:
    """Build a fresh, fully-populated `CollabState` for a new run.

    Every channel is initialised (LangGraph requires the full schema on first
    invoke). Defaults follow ARCH §8: `max_rounds=3`, `τ=0.85`.
    """
    return CollabState(
        goal=goal,
        success_criteria=list(success_criteria or []),
        agent_task_framing={},
        contributions=[],
        critiques=[],
        round=0,
        max_rounds=max_rounds,
        confidence_threshold=confidence_threshold,
        converged=False,
        consensus_ranking=[],
        status="init",
        active_agent_ids=list(active_agent_ids),
        final_output=None,
        hitl_enabled=hitl_enabled,
        hitl_decision=None,
        events=[],
    )


def make_event(event_type: str, **data: Any) -> dict[str, Any]:
    """Build a minimal AG-UI-shaped event record for the `events` channel.

    The full envelope (session_id, run_id, seq, ts) is added by the streaming
    layer in Step 8 (ARCH §24.3); here we only persist `{type, data}` so the
    foundation slice already produces an inspectable event trail.
    """
    return {"type": event_type, "data": dict(data)}


def text_block(text: str) -> dict[str, Any]:
    """A §24.6 ``text`` content block — the minimal renderable body of a
    ``contribution`` / ``synthesis`` event.

    The content-block array is the A2UI seam (ARCH §24.6): the React renderer
    switches on each block's ``type``. A plain ``text`` block is the faithful
    minimum for an agent's proposal or the synthesized output; richer block types
    (``code``, ``tool_result``) extend the same union without a contract change.
    """
    return {"type": "text", "text": text}


def latest_round_contributions(state: Mapping[str, Any]) -> list[Contribution]:
    """Return contributions tagged with the state's current `round` (ARCH §8).

    Used by ``consensus_node`` *after* a round's parallel writes have joined, so
    ``round`` then identifies the just-completed round's contributions.
    """
    current = state["round"]
    return [c for c in state["contributions"] if c["round"] == current]


def ranked_contributions(state: Mapping[str, Any]) -> list[Contribution]:
    """Resolve ``consensus_ranking`` keys to ``Contribution`` objects, best first.

    ``consensus_node`` records the ranking as ``"agent_id:round"`` keys (ARCH §8).
    The synthesizer needs the actual contribution bodies to merge, in that order;
    this maps each key back to its contribution and drops any that cannot be
    resolved (defensive — a malformed key should not crash synthesis).
    """
    by_key = {f"{c['agent_id']}:{c['round']}": c for c in state["contributions"]}
    return [by_key[key] for key in state["consensus_ranking"] if key in by_key]


def previous_round_contributions(state: Mapping[str, Any]) -> list[Contribution]:
    """Return the immediately-preceding round's contributions (ARCH §2.1 / §23.4).

    This is what a peer should read *while* a round is in flight. During the
    ``Send()`` fan-out for round N, the blackboard's ``round`` is N but round-N
    contributions do not exist yet — they are being produced in parallel and are
    "eventually visible next round" (ARCH §23.4). The peers' latest *visible*
    work is therefore round N-1. For the opening round (N=1) this is empty, which
    the prompt renders as "this is the opening round".
    """
    previous = state["round"] - 1
    return [c for c in state["contributions"] if c["round"] == previous]
