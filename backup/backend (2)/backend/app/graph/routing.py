"""Conditional-edge functions for the collaboration graph (ARCHITECTURE.md §7).

These two functions are where the "DAG-vs-mesh reconciliation" (ARCH §2.1) is
realised:

* ``fan_out_to_mesh`` turns one super-step into the **inner mesh** — a parallel
  ``Send()`` fan-out to every active agent, each receiving the whole blackboard.
  There are no fixed agent-to-agent edges; the mesh is "every agent reads/writes
  one shared structure".
* ``route_after_consensus`` is the **outer loop** — it either runs another debate
  round (fan out again) or proceeds to the HITL gate when the run has converged
  or hit ``max_rounds``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from langgraph.types import Send

from app.graph.state import CollabState, all_abstained, previous_round_contributions


def will_run_another_round(state: Mapping[str, Any]) -> bool:
    """The outer-loop predicate — the **single source of truth** for "loop again?".

    Another debate round runs iff the run has **not** converged and has **not** yet
    run ``max_rounds`` rounds (locked §3: "loop until rounds ≥ N" → exactly N rounds).
    Read against the *post-increment* ``round`` (``consensus_node`` advances ``round``
    before this is evaluated): after round K, ``round == K+1``, so ``K+1 <= N`` keeps
    looping through round N and stops once ``round`` would exceed N. ``max_rounds=N``
    therefore runs **N** debate rounds (Bug 4 — ``<`` previously ran only N-1).
    Both :func:`route_after_consensus` and ``consensus_node`` (which emits the next
    ``round_start``) read this one predicate, so they can never disagree.
    """
    return not state["converged"] and state["round"] <= state["max_rounds"]


def fan_out_to_mesh(state: CollabState) -> list[Send]:
    """Fan out to every active agent in parallel — the mesh, no fixed edges.

    Each ``Send`` payload is ``{"agent_id": aid, **state}``: the agent's id plus a
    full copy of the blackboard so the agent can read every peer's latest work.
    The extra ``agent_id`` key is carried through to the node untouched (verified
    against langgraph 1.2.5) and read by ``agent_turn_node``.
    """
    return [Send("agent_turn", {"agent_id": aid, **state}) for aid in state["active_agent_ids"]]


def route_after_consensus(state: CollabState) -> list[Send] | str:
    """Loop for another round, or proceed to the HITL gate.

    Termination (ARCH §8, locked): stop when the run has ``converged`` **or**
    ``round >= max_rounds``. Note that ``consensus_node`` has already incremented
    ``round`` before this runs, so the comparison is against the post-increment
    counter exactly as written in ARCH §7's reference code — expressed once in
    :func:`will_run_another_round`.

    Rate-limit cascade guard (§21.5): additionally stop when the just-completed round
    was entirely abstentions (e.g. every agent 429'd) — another round would fail the
    same way. ``consensus_node`` incremented ``round``, so the just-completed round's
    contributions are the *previous* round; this mirrors the ``stalled`` check there
    so the router and the ``round_start`` emission never disagree.
    """
    if all_abstained(previous_round_contributions(state)):
        return "hitl"
    if will_run_another_round(state):
        return fan_out_to_mesh(state)
    return "hitl"
