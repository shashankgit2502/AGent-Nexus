"""Orchestrator node — the entry node (ARCHITECTURE.md §4.1).

LOCKED ROLE (CLAUDE.md §3): the Orchestrator is an *entry node only* — a prompt
engineer + agent spawner that goes **passive** after dispatch. It is NOT a
runtime controller and never re-enters the loop.

Step-2 stub scope
-----------------
Real prompt-engineering (per-persona task framing on the cheap ``small_model``)
and runtime agent spawning land in Step 4 (Agent factory, ARCH §22). Here the
node only: seeds trivial per-agent framing, marks the run ``debating``, opens
round 1, and emits the ``run_start`` event. ``active_agent_ids`` is supplied in
the initial state for the foundation slice.
"""

from __future__ import annotations

from typing import Any

from app.graph.state import CollabState, make_event


def orchestrator_node(state: CollabState) -> dict[str, Any]:
    """Frame the goal for each agent and open the first debate round."""
    goal = state["goal"]
    roster = state["active_agent_ids"]

    framing = {aid: f"You are agent '{aid}'. Collaborate toward the goal: {goal}" for aid in roster}

    return {
        "agent_task_framing": framing,
        "round": 1,
        "status": "debating",
        # ``run_start`` opens the run; ``round_start`` opens round 1 (ARCH §24.4).
        # Subsequent rounds' ``round_start`` events are emitted by ``consensus_node``
        # when the outer loop continues — the orchestrator stays an entry node only.
        "events": [
            make_event("run_start", goal=goal, roster=roster),
            make_event("round_start", round=1),
        ],
    }
