"""Consensus node — convergence check + confidence-weighted ranking (ARCH §8).

Runs alone after every mesh round (all parallel ``agent_turn`` nodes join here),
so it may safely write scalar channels. Implements the locked math from ARCH §8:

* **Termination signal** — ``converged`` is true when the mean self-confidence of
  this round's contributions reaches τ (``confidence_threshold``).
* **Selection** — a confidence-weighted ranking of this round's contributions,
  best first, handed to the synthesizer as ``consensus_ranking``.

It also advances ``round`` by one (ARCH §8 reference code). ``route_after_consensus``
(app/graph/routing.py) reads the post-increment counter to decide loop-vs-proceed.
"""

from __future__ import annotations

from typing import Any

from app.graph.routing import will_run_another_round
from app.graph.state import CollabState, latest_round_contributions, make_event


def consensus_node(state: CollabState) -> dict[str, Any]:
    """Compute convergence + weighted ranking for the current round."""
    latest = latest_round_contributions(state)

    mean_confidence = sum(c["confidence"] for c in latest) / len(latest) if latest else 0.0
    converged = mean_confidence >= state["confidence_threshold"]

    # Confidence-weighted ranking (weights normalise but preserve order).
    total = sum(c["confidence"] for c in latest) or 1.0
    ranked = sorted(latest, key=lambda c: c["confidence"] / total, reverse=True)
    ranking = [f"{c['agent_id']}:{c['round']}" for c in ranked]

    next_round = state["round"] + 1
    events = [
        make_event(
            "consensus_update",
            mean_confidence=mean_confidence,
            converged=converged,
            ranking=ranking,
        )
    ]
    # If the outer loop will run again, open the next round here (the routing
    # function can't emit events). Evaluated against the post-increment counter via
    # the shared predicate so it can never disagree with ``route_after_consensus``.
    if will_run_another_round(
        {"converged": converged, "round": next_round, "max_rounds": state["max_rounds"]}
    ):
        events.append(make_event("round_start", round=next_round))

    return {
        "converged": converged,
        "consensus_ranking": ranking,
        "round": next_round,
        "status": "consensus",
        "events": events,
    }
