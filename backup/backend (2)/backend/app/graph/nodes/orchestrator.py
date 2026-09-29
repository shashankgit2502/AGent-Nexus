"""Orchestrator node — the entry node (ARCHITECTURE.md §4.1).

LOCKED ROLE (CLAUDE.md §3): the Orchestrator is an *entry node only* — a prompt
engineer + agent spawner that goes **passive** after dispatch. It is NOT a runtime
controller and never re-enters the loop.

What it does (one decision, made once)
--------------------------------------
1. Ask the injected :class:`~app.graph.context.Planner` how this goal maps onto this
   roster: a strategy (decompose / debate / single_owner), per-agent subtasks with
   phases and acceptance checks, and the target deliverable.
2. Render that plan into per-agent framing (:mod:`app.agents.framing`) on the
   existing ``agent_task_framing`` channel, which the per-round prompt already reads.
3. Publish the plan on the blackboard, open round 1, and step aside.

There is no master — but there *is* an informed starting point. Every downstream
node reads the plan off the shared blackboard; the orchestrator never runs again.

Why this is not a controller (R4)
---------------------------------
The plan is a **suggestion posted to the blackboard before any agent runs**, not a
runtime instruction stream. Nothing waits on the orchestrator, nothing routes through
it, and ``depends_on`` is context for the agent rather than a scheduling constraint
(the mesh is a parallel ``Send()`` fan-out — ARCH §23.4). Peers stay free to deviate,
critique, and cover gaps.

Degradation (R3 — honest, never silent)
---------------------------------------
No planner in the runtime context (foundation tests, a team with no viable model)
⇒ :func:`~app.agents.plan.fallback_plan`: a real ``debate`` plan carrying a warning
that no decomposition happened, rather than a fake decomposition or the old
identical-string stub. A planner that *fails* degrades the same way — planning is a
quality step and must never cost availability.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from langgraph.runtime import Runtime

from app.agents.framing import render_agent_framing
from app.agents.plan import RunPlan, fallback_plan
from app.graph.context import MeshContext
from app.graph.state import CollabState, make_event

logger = logging.getLogger(__name__)


def _plan_event(plan: RunPlan) -> dict[str, Any]:
    """The AG-UI ``plan_ready`` record (§24.4) — what the Workspace plan panel renders.

    Emitted before ``round_start`` so the client can show *who is doing what* the
    moment the run opens, instead of inferring it from contributions after the fact.
    """
    return make_event(
        "plan_ready",
        strategy=plan.strategy,
        summary=plan.summary,
        subtasks=[
            {
                "id": task.id,
                "title": task.title,
                "instruction": task.instruction,
                "agent_id": task.assigned_agent_id,
                "round": task.round_hint,
                "depends_on": list(task.depends_on),
                "acceptance": list(task.acceptance),
            }
            for task in plan.subtasks
        ],
        deliverable={
            "kind": plan.deliverable.kind,
            "filename": plan.deliverable.filename,
            "notes": plan.deliverable.notes,
        },
        warnings=list(plan.warnings),
    )


def _dispatch(state: Mapping[str, Any], plan: RunPlan) -> dict[str, Any]:
    """Turn a resolved plan into the orchestrator's blackboard update + opening events.

    Shared by the sync and async nodes so both paths produce a byte-identical update
    and the only difference between them is how the plan was obtained.
    """
    goal = str(state["goal"])
    roster: Sequence[str] = list(state["active_agent_ids"])
    names = _agent_names(state)

    framing = render_agent_framing(plan, goal=goal, roster=roster, names=names)

    for warning in plan.warnings:
        logger.warning("run plan warning: %s", warning)

    return {
        "agent_task_framing": framing,
        "plan": plan.as_state(),
        "round": 1,
        "status": "debating",
        # ``run_start`` opens the run, ``plan_ready`` publishes the assignment, and
        # ``round_start`` opens round 1 (ARCH §24.4). Later rounds' ``round_start``
        # come from ``consensus_node`` — the orchestrator stays an entry node only.
        "events": [
            make_event("run_start", goal=goal, roster=list(roster)),
            _plan_event(plan),
            make_event("round_start", round=1),
        ],
    }


def _agent_names(state: Mapping[str, Any]) -> dict[str, str]:
    """Optional agent_id → display name map for readable framing.

    The blackboard carries ids; names are a presentation nicety supplied by the
    composition root when available. Absent ⇒ framing falls back to short ids.
    """
    names = state.get("agent_names")
    if isinstance(names, Mapping):
        return {str(k): str(v) for k, v in names.items()}
    return {}


def _planning_inputs(state: Mapping[str, Any]) -> tuple[str, list[str], int]:
    """Extract ``(goal, success_criteria, max_rounds)`` for the planning call."""
    goal = str(state["goal"])
    criteria = [str(c) for c in (state.get("success_criteria") or [])]
    max_rounds = int(state.get("max_rounds", 3) or 3)
    return goal, criteria, max_rounds


def orchestrator_node(state: CollabState, runtime: Runtime[MeshContext]) -> dict[str, Any]:
    """Plan the run and open round 1 (synchronous ``invoke`` path)."""
    planner = runtime.context.planner if runtime.context is not None else None
    goal, criteria, max_rounds = _planning_inputs(state)

    if planner is None:
        plan = fallback_plan(goal, list(state["active_agent_ids"]))
    else:
        plan = planner.plan(goal=goal, success_criteria=criteria, max_rounds=max_rounds)
    return _dispatch(state, plan)


async def aorchestrator_node(state: CollabState, runtime: Runtime[MeshContext]) -> dict[str, Any]:
    """Plan the run and open round 1 (async ``astream`` path — the real runs).

    Registered alongside :func:`orchestrator_node` via ``RunnableCallable`` so the
    call style picks the implementation, mirroring ``agent_turn`` and ``synthesizer``.
    Planning is one awaited model call; everything after it is identical.
    """
    planner = runtime.context.planner if runtime.context is not None else None
    goal, criteria, max_rounds = _planning_inputs(state)

    if planner is None:
        plan = fallback_plan(goal, list(state["active_agent_ids"]))
    else:
        plan = await planner.aplan(goal=goal, success_criteria=criteria, max_rounds=max_rounds)
    return _dispatch(state, plan)
