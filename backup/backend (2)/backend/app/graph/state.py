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

from app.a2a.messages import A2AMessage

# A round's lifecycle phase. Mirrors the AG-UI run progression (ARCH §24.4).
RunStatus = Literal["init", "debating", "consensus", "hitl", "synth", "done"]


class Contribution(TypedDict):
    """One agent's proposal for one round (ARCH §6)."""

    agent_id: str
    round: int
    # Which run produced this (ARCH §22.5). A checkpointer thread hosts MANY runs and
    # ``round`` restarts at 1 each time, so ``round`` alone cannot identify a run's work.
    # NotRequired: contributions written before this channel existed carry no run_id and
    # are excluded once run scoping is active (see :func:`in_run`).
    run_id: NotRequired[str | None]
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
    # Run scoping, as on ``Contribution`` (ARCH §22.5). Critiques are rendered back to
    # their target in the round prompt; without this a peer would be shown criticism
    # from a *previous* run on the same thread.
    run_id: NotRequired[str | None]


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

    # ── Run identity (ARCH §22.5) ────────────────────────────────────────────
    # The checkpointer ``thread_id`` is per **Session** and per **Conversation**, and a
    # thread hosts MANY runs — while the additive channels below persist across all of
    # them and ``round`` restarts at 1 every run. Without this channel, run 2's
    # ``(agent_id, round=1)`` collides with run 1's: the ``agent_turn`` idempotency guard
    # skips every agent, and consensus ranks the PREVIOUS run's contributions. The
    # observable symptom was the second query on a session — and every chat turn after
    # the first — silently returning the first run's answer.
    #
    # ``None`` = no run scoping (callers that don't supply one, e.g. foundation tests),
    # which reproduces the pre-scoping behaviour exactly. See :func:`in_run`.
    run_id: str | None

    # ── Goal & framing (written by the Orchestrator entry node) ──────────────
    goal: str
    success_criteria: list[str]
    agent_task_framing: dict[str, str]  # agent_id -> tailored prompt
    # agent_id -> display name. Presentation metadata carried on the blackboard so the
    # orchestrator can render readable framing ("Legal Reviewer", not a raw UUID)
    # without a DB read inside the graph. Empty when the caller supplies none.
    agent_names: dict[str, str]
    # The run plan (ARCH §4.1): strategy, per-agent subtasks, and the target
    # deliverable, decided ONCE by the orchestrator before dispatch. Held as a plain
    # dict (``RunPlan.as_state()``) so the Postgres checkpointer never depends on a
    # Pydantic round-trip; readers rebuild it with ``plan_from_state`` and MUST use
    # ``state.get("plan")`` — a checkpoint written before this channel existed has none.
    plan: dict[str, Any] | None
    # The acceptance verdict on the plan's ``acceptance`` criteria (ARCH §4.1), written by
    # the consensus node on the terminal round and read by the HITL gate so the human
    # approves against evidence rather than impression. ``None`` = not verified (no plan
    # criteria, no verifier wired, or verification failed) — which must never be rendered
    # as "passed". Held as a plain dict (``AcceptanceReport.as_state()``) for the same
    # checkpointer-safety reason as ``plan``.
    acceptance: dict[str, Any] | None

    # ── Mesh working memory (append-only, parallel-safe) ─────────────────────
    contributions: Annotated[list[Contribution], add]
    critiques: Annotated[list[Critique], add]
    # Typed inter-agent messages (ARCH §23) — the channel that lets peers ask, hand off,
    # and endorse rather than only propose and criticise. Additive for the same reason as
    # ``contributions``: every agent in a round writes it concurrently.
    #
    # Readers MUST use ``state.get("messages", [])`` — a checkpoint written before this
    # channel existed has none, and a resumed run must degrade to "no messages" rather
    # than raise (the same tolerance ``plan`` established).
    messages: Annotated[list[A2AMessage], add]

    # ── Consensus bookkeeping ────────────────────────────────────────────────
    round: int
    max_rounds: int
    confidence_threshold: float  # τ
    converged: bool
    consensus_ranking: list[str]  # "agent_id:round", best first
    # Per-peer contribution length cap (chars) applied when rendering rounds ≥ 2 into
    # the prompt (app/agents/prompts.py). A run-tuning parameter (like max_rounds); 0 =
    # no cap. Carried on the blackboard so the per-round prompt reads it directly
    # without threading a setting through the runner/runtime call chain.
    peer_content_max_chars: int

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
    peer_content_max_chars: int = 0,
    agent_names: Mapping[str, str] | None = None,
    run_id: str | None = None,
) -> CollabState:
    """Build a fresh, fully-populated `CollabState` for a new run.

    Every channel is initialised (LangGraph requires the full schema on first
    invoke). `max_rounds=3` follows ARCH §8; `τ` is back to the locked **0.85**.

    Why it moved back (R3): τ had been raised to 0.95 to stop well-calibrated models
    converging on their own inflated self-assessment. That treated the symptom — the
    *metric* was the problem, not the threshold. Scores are now peer-adjusted (§8.1:
    ENDORSE/VOTE raise, CRITIQUE lowers), so an agent can no longer clear the bar on
    self-belief alone and the compensation is no longer needed. Leaving τ at 0.95 on top
    of a corrected metric would make convergence unreachable for a different reason.

    ``peer_content_max_chars`` (0 = no cap) bounds how much of each peer's proposal
    is rendered into rounds ≥ 2 to shrink per-request tokens under a rate budget.

    ``run_id`` scopes every round-keyed read to THIS run (ARCH §22.5). Real callers
    (``run_service``/``chat``) pass the ``runs`` row id; omitting it disables scoping and
    reproduces the previous behaviour, which keeps foundation tests unchanged.
    """
    return CollabState(
        run_id=run_id,
        goal=goal,
        success_criteria=list(success_criteria or []),
        agent_task_framing={},
        agent_names=dict(agent_names or {}),
        plan=None,  # written by the orchestrator on its single planning pass
        acceptance=None,  # written by the consensus node on the terminal round
        contributions=[],
        critiques=[],
        messages=[],
        round=0,
        max_rounds=max_rounds,
        confidence_threshold=confidence_threshold,
        converged=False,
        consensus_ranking=[],
        peer_content_max_chars=peer_content_max_chars,
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


def in_run(item: Mapping[str, Any], run_id: str | None) -> bool:
    """True if ``item`` belongs to ``run_id`` — the run-scoping predicate (ARCH §22.5).

    This is the **single source of truth** for "does this blackboard record belong to the
    run currently executing?", shared by every round-keyed reader so they can never
    disagree with the ``agent_turn`` idempotency guard.

    Two deliberate cases:

    * ``run_id is None`` — the caller did not scope this run (foundation tests, any
      pre-existing call site). Everything matches, which is **exactly** the behaviour
      before run scoping existed. This is what keeps the change backward compatible.
    * ``run_id`` set — only records stamped with the *same* id match. Records carrying no
      ``run_id`` are from a run that predates this channel, so they are correctly excluded
      rather than leaking into the current run.
    """
    if run_id is None:
        return True
    return item.get("run_id") == run_id


def current_run_id(state: Mapping[str, Any]) -> str | None:
    """This state's run id, or ``None`` when the run is unscoped (legacy/tests)."""
    value = state.get("run_id")
    return str(value) if value is not None else None


def latest_round_contributions(state: Mapping[str, Any]) -> list[Contribution]:
    """Return this run's contributions tagged with the current `round` (ARCH §8).

    Used by ``consensus_node`` *after* a round's parallel writes have joined, so
    ``round`` then identifies the just-completed round's contributions.

    Scoped to the current run (§22.5): a thread hosts many runs and ``round`` restarts at
    1 in each, so filtering on ``round`` alone would mix a previous run's work into this
    run's consensus.
    """
    current = state["round"]
    run = current_run_id(state)
    return [c for c in state["contributions"] if c["round"] == current and in_run(c, run)]


def ranked_contributions(state: Mapping[str, Any]) -> list[Contribution]:
    """Resolve ``consensus_ranking`` keys to ``Contribution`` objects, best first.

    ``consensus_node`` records the ranking as ``"agent_id:round"`` keys (ARCH §8).
    The synthesizer needs the actual contribution bodies to merge, in that order;
    this maps each key back to its contribution and drops any that cannot be
    resolved (defensive — a malformed key should not crash synthesis).

    Scoped to the current run (§22.5): the ranking key is ``agent_id:round``, which is
    **ambiguous across runs on one thread** (run 1 and run 2 both have an ``a:1``). Without
    scoping, the synthesizer could be handed a previous run's answer to merge.
    """
    run = current_run_id(state)
    by_key = {
        f"{c['agent_id']}:{c['round']}": c for c in state["contributions"] if in_run(c, run)
    }
    return [by_key[key] for key in state["consensus_ranking"] if key in by_key]


def all_abstained(contributions: list[Contribution]) -> bool:
    """True if every contribution in ``contributions`` is a confidence-0 abstention.

    A round where *every* agent abstained (e.g. all rate-limited, §21.5) carries no
    real signal: its mean confidence is 0, it cannot converge, and — critically —
    running another identical round would fail the same way, burning more of the
    provider budget for nothing (the rate-limit cascade). The consensus loop uses
    this to stop early and hand what exists to the human gate instead of hammering.

    An empty list returns ``False`` (nothing ran ⇒ not a stall). The abstention path
    (:func:`app.graph.nodes.agent_turn._abstention_update`) sets confidence exactly
    ``0.0``, so an all-zero round is precisely an all-abstention round.
    """
    return bool(contributions) and all(c["confidence"] == 0.0 for c in contributions)


def previous_round_contributions(state: Mapping[str, Any]) -> list[Contribution]:
    """Return the immediately-preceding round's contributions (ARCH §2.1 / §23.4).

    This is what a peer should read *while* a round is in flight. During the
    ``Send()`` fan-out for round N, the blackboard's ``round`` is N but round-N
    contributions do not exist yet — they are being produced in parallel and are
    "eventually visible next round" (ARCH §23.4). The peers' latest *visible*
    work is therefore round N-1. For the opening round (N=1) this is empty, which
    the prompt renders as "this is the opening round".

    Scoped to the current run (§22.5), so the opening round of run 2 never sees run 1's
    contributions as if they were "the previous round".
    """
    previous = state["round"] - 1
    run = current_run_id(state)
    return [c for c in state["contributions"] if c["round"] == previous and in_run(c, run)]


def run_critiques(state: Mapping[str, Any]) -> list[Critique]:
    """Critiques belonging to the current run (ARCH §22.5).

    ``render_round_message`` shows an agent the critiques aimed at it. Unscoped, that
    included criticism raised in a *previous* run on the same thread — stale feedback
    about work the agent is no longer doing.
    """
    run = current_run_id(state)
    return [c for c in (state.get("critiques") or []) if in_run(c, run)]


def run_messages(state: Mapping[str, Any]) -> list[A2AMessage]:
    """A2A messages belonging to the current run (ARCH §23 / §22.5).

    ``state.get`` (not ``state[...]``) because a checkpoint written before the ``messages``
    channel existed has none, and a resumed run must degrade to "no messages" rather than
    raise. Run-scoped for the same reason contributions are: a thread hosts many runs, so
    without it an agent's inbox would carry a *previous* run's requests — an agent being
    asked, in round 2 of today's audit, for a number someone needed last week.
    """
    run = current_run_id(state)
    return [m for m in (state.get("messages") or []) if in_run(m, run)]
