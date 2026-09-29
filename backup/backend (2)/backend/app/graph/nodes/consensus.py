"""Consensus node — convergence check + confidence-weighted ranking (ARCH §8).

Runs alone after every mesh round (all parallel ``agent_turn`` nodes join here),
so it may safely write scalar channels. Implements the locked math from ARCH §8:

* **Termination signal** — ``converged`` requires three things (§8.1): the round is ≥ 2,
  the mean *peer-adjusted* score reaches τ (``confidence_threshold``), and the team agrees
  on the same candidate (or nobody voted, in which case that gate is skipped).
* **Selection** — a peer-weighted ranking of this round's contributions, best first,
  handed to the synthesizer as ``consensus_ranking``.

The maths lives in :mod:`app.consensus.scoring` (pure, no graph imports); this node is the
thin adapter that reads the blackboard, calls it, and projects the result into events.

It also advances ``round`` by one (ARCH §8 reference code). ``route_after_consensus``
(app/graph/routing.py) reads the post-increment counter to decide loop-vs-proceed.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from langgraph.runtime import Runtime

from app.agents.acceptance import evidence_from_contributions
from app.agents.plan import apply_delegations, plan_from_state
from app.consensus.scoring import score_round
from app.graph.context import MeshContext
from app.graph.routing import will_run_another_round
from app.graph.state import (
    CollabState,
    all_abstained,
    current_run_id,
    latest_round_contributions,
    make_event,
    run_critiques,
    run_messages,
)

logger = logging.getLogger(__name__)


def _amend_plan(state: CollabState, current_round: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fold this round's peer hand-offs into the plan (ARCH §4.1 / Finding 8).

    Runs in the consensus node because this node executes **alone** after the round's
    parallel writes have joined — so it may safely write the scalar ``plan`` channel, which
    a fanned-out ``agent_turn`` never can. The orchestrator is not re-entered: peers amend
    the plan through the blackboard, which keeps §3's "entry node, not a controller".

    Returns ``({}, [])`` when nothing was delegated, so an unchanged plan is never rewritten.
    """
    plan = plan_from_state(state.get("plan"))
    if plan is None:
        return {}, []
    amended, events = apply_delegations(
        plan,
        messages=run_messages(state),
        roster=[str(a) for a in (state.get("active_agent_ids") or [])],
        max_rounds=int(state.get("max_rounds", 3) or 3),
        current_round=current_round,
    )
    if not events or amended is None:
        return {}, []
    for record in events:
        logger.info(
            "plan amended in round %s by %s: %s", record["round"], record["by_agent"], record["change"]
        )
    return {"plan": amended.as_state()}, [make_event("plan_amended", **record) for record in events]


def _acceptance_update(report: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Project an :class:`AcceptanceReport` into a state update + event, if it has content.

    An empty report (no plan criteria, no verifier, or verification failed) writes nothing
    and emits nothing: the absence of a report is how the UI tells "unverified" from
    "verified and passing", and fabricating an all-clear would erase that distinction.
    """
    if report is None or not getattr(report, "checks", ()):
        return {}, []
    state_value = report.as_state()
    return {"acceptance": state_value}, [make_event("acceptance_report", **state_value)]


def consensus_node(
    state: CollabState, runtime: Runtime[MeshContext] | None = None
) -> dict[str, Any]:
    """Compute convergence + peer-weighted ranking for the current round (§8/§8.1).

    ``runtime`` is accepted but unused: ``RunnableCallable`` dispatches on the *sync*
    signature, so both twins must take the same arguments. It defaults to ``None`` so the
    node stays directly callable as ``consensus_node(state)`` — this node is pure scoring
    and needs no injected dependency; only the async twin does (the verifier).
    """
    latest = latest_round_contributions(state)
    current_round = state["round"]

    # Peer-weighted scoring (§8.1). Self-confidence remains the base term; ENDORSE/VOTE
    # raise it and CRITIQUE lowers it, so a hallucinating agent that self-rates 0.95 no
    # longer outranks a careful peer the team actually backed. With no A2A signal every
    # delta is 0 and this reduces exactly to the previous self-confidence ranking — the
    # backward-compatible path, structural rather than special-cased.
    #
    # Round-1 never converges because peers are only visible next round (§23.4): the rule
    # is enforced inside ``score_round`` where the reason lives, not as a bare guard here.
    result = score_round(
        latest,
        messages=run_messages(state),
        critiques=run_critiques(state),
        current_round=current_round,
        run_id=current_run_id(state),
        roster_size=len(state.get("active_agent_ids") or []),
        confidence_threshold=state["confidence_threshold"],
    )
    converged = result.converged
    ranking = result.ranking

    # Rate-limit cascade guard (§21.5): if EVERY agent abstained this round (e.g. all
    # 429'd), the round has no signal and another round would fail identically. Stop
    # the debate loop and proceed to the human gate rather than burning more of the
    # provider budget on doomed rounds. Shared predicate with ``route_after_consensus``
    # (both read the same just-completed round) so the router and this node's
    # ``round_start`` emission can never disagree.
    stalled = all_abstained(latest)

    next_round = state["round"] + 1
    events = [
        make_event(
            "consensus_update",
            # ``mean_confidence`` keeps its original meaning (the raw self-reported mean)
            # so existing consumers and replays are unaffected; the peer-weighted view is
            # carried alongside in additive fields.
            mean_confidence=result.mean_confidence,
            converged=converged,
            ranking=ranking,
            mean_score=result.mean_score,
            peer_scores=result.scores,
            peer_deltas=result.peer_deltas,
            agreement=result.agreement,
            tally=result.tally,
        )
    ]
    if stalled:
        # Terminal for the loop: surface WHY the debate is stopping early so the UI can
        # show "every agent abstained (e.g. rate-limited) — stopping" instead of a
        # silent jump to the gate. ``route_after_consensus`` makes the matching routing
        # decision, so no ``round_start`` is emitted here.
        events.append(
            make_event(
                "consensus_stalled",
                round=current_round,
                mean_confidence=result.mean_confidence,
                message=(
                    "every agent abstained this round (e.g. all rate-limited); "
                    "stopping the debate loop instead of retrying identical rounds"
                ),
            )
        )
    # If the outer loop will run again, open the next round here (the routing
    # function can't emit events). Evaluated against the post-increment counter via
    # the shared predicate so it can never disagree with ``route_after_consensus``.
    elif will_run_another_round(
        {"converged": converged, "round": next_round, "max_rounds": state["max_rounds"]}
    ):
        events.append(make_event("round_start", round=next_round))

    # Peer re-planning (Finding 8): fold any DELEGATE hand-offs from this round into the
    # plan, so the assignment the UI shows stays true to what the team is actually doing.
    plan_update, plan_events = _amend_plan(state, current_round)
    events.extend(plan_events)

    return {
        "converged": converged,
        "consensus_ranking": ranking,
        "round": next_round,
        "status": "consensus",
        **plan_update,
        "events": events,
    }


def _is_terminal(state: CollabState, update: Mapping[str, Any]) -> bool:
    """True when this round is the last one — i.e. the run now proceeds to the HITL gate.

    Derived from the *same* predicate the router uses (``will_run_another_round``) plus the
    all-abstained stall guard, so "was that the final round?" can never disagree with where
    the graph actually goes next. Computed rather than passed back on the update dict: the
    update is written to ``CollabState``, and a private bookkeeping key would be an unknown
    channel.
    """
    if all_abstained(latest_round_contributions(state)):
        return True
    return not will_run_another_round(
        {
            "converged": bool(update["converged"]),
            "round": int(update["round"]),
            "max_rounds": int(state["max_rounds"]),
        }
    )


async def aconsensus_node(state: CollabState, runtime: Runtime[MeshContext]) -> dict[str, Any]:
    """Consensus + (on the terminal round) acceptance verification (§8/§8.1 / §4.1).

    Registered alongside :func:`consensus_node` via ``RunnableCallable`` so the call style
    picks the implementation — mirroring ``orchestrator`` / ``agent_turn`` / ``synthesizer``.
    The scoring is identical; the only addition is one awaited verifier call.

    Why acceptance runs **here** and not in the HITL node, where its output is consumed:
    ``hitl_node`` builds its review payload *before* ``interrupt()``, and LangGraph
    re-executes a node from the top on resume — so a model call there would fire twice and
    bill twice for one run. Consensus runs exactly once per round, so the terminal round is
    the last point at which the work can be verified once.

    It is a **sub-step of consensus, not a new node**, so the locked control graph
    (Orchestrator → Mesh ↺ Consensus → HITL → Synthesizer → End) is unchanged — the same
    precedent ARTIFACTS §2A set by making the artifact producer a sub-step of synthesis.
    """
    update = consensus_node(state)

    verifier = runtime.context.verifier if runtime.context is not None else None
    if verifier is None or not _is_terminal(state, update):
        return update

    # Verify against the CONSENSUS-RANKED result, not one agent's draft: the criteria
    # describe what the *team* had to deliver, and in a decomposed plan no single
    # contribution satisfies all of them.
    ranked_keys = update.get("consensus_ranking") or []
    by_key = {f"{c['agent_id']}:{c['round']}": c for c in state["contributions"]}
    ranked = [by_key[key] for key in ranked_keys if key in by_key]
    # Read the plan from THIS update when it was just amended, so a delegated subtask's
    # criteria are verified too rather than being judged against a stale plan.
    plan = plan_from_state(update.get("plan", state.get("plan")))

    report = await verifier.averify(
        goal=str(state["goal"]),
        plan=plan,
        result=evidence_from_contributions(ranked),
    )
    acceptance_update, acceptance_events = _acceptance_update(report)
    if acceptance_events:
        logger.info(
            "acceptance verified: %s/%s criteria met",
            acceptance_update["acceptance"]["met_count"],
            acceptance_update["acceptance"]["total"],
        )
    return {
        **update,
        **acceptance_update,
        "events": [*update["events"], *acceptance_events],
    }
