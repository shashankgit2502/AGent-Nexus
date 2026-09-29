"""Slice-0 unit tests: round/turn boundary events (ARCH §24.4).

Lock the placement of the two graph-structural markers the runner streams:

* ``round_start`` — opened by the orchestrator for round 1 and by ``consensus_node``
  for every subsequent round, **only** when the outer loop will actually run again
  (shared predicate ``will_run_another_round`` — no drift with the router).
* ``agent_turn_start`` — prepended by ``agent_turn_node`` on every path (stub and
  abstention included) so each agent's turn is bracketed before its inner events.
"""

from __future__ import annotations

from typing import Any

from app.graph.context import MeshContext
from app.graph.nodes.agent_turn import agent_turn_node
from app.graph.nodes.consensus import consensus_node
from app.graph.nodes.orchestrator import orchestrator_node


class _FakeRuntime:
    """Minimal stand-in exposing only ``.context`` (what the node reads)."""

    def __init__(self, context: MeshContext) -> None:
        self.context = context


class _RaisingRunner:
    """A runner that always fails → exercises the abstention path."""

    def run(self, agent_id: str, blackboard: Any) -> dict[str, Any]:  # noqa: ANN401
        raise RuntimeError("model exploded")


def _consensus_state(*, round_: int = 1, confidence: float = 0.5, **over: Any) -> dict[str, Any]:
    """A consensus-node input whose contribution always belongs to the CURRENT round.

    ``consensus_node`` scores only ``latest_round_contributions`` (contributions
    tagged with ``state['round']``), so the contribution's round must track the
    state's or the node sees an empty round and scores 0.0.
    """
    base: dict[str, Any] = {
        "round": round_,
        "max_rounds": 3,
        "confidence_threshold": 0.85,
        "contributions": [
            {
                "agent_id": "a",
                "round": round_,
                "content": "x",
                "confidence": confidence,
                "tool_calls": [],
            },
        ],
    }
    base.update(over)
    return base


# ── orchestrator opens round 1 ───────────────────────────────────────────────


def test_orchestrator_emits_run_start_plan_ready_then_round_start_one() -> None:
    # ``planner=None`` ⇒ the unplanned fallback (every agent addresses the whole
    # goal), which is the path that needs no model. The node still publishes a plan,
    # so ``plan_ready`` sits between ``run_start`` and round 1's ``round_start``
    # (ARCH §24.4).
    update = orchestrator_node(
        {"goal": "g", "active_agent_ids": ["a", "b"]},  # type: ignore[arg-type]
        _FakeRuntime(MeshContext()),  # type: ignore[arg-type]
    )

    assert update["round"] == 1
    assert [e["type"] for e in update["events"]] == ["run_start", "plan_ready", "round_start"]
    assert update["events"][2]["data"] == {"round": 1}


# ── consensus opens the next round only when the loop continues ───────────────


def test_consensus_emits_round_start_for_next_round_when_looping() -> None:
    # mean confidence 0.5 < τ 0.85 → not converged; next_round 2 < max 3 → loop.
    update = consensus_node(_consensus_state())  # type: ignore[arg-type]

    assert update["round"] == 2
    types = [e["type"] for e in update["events"]]
    assert types == ["consensus_update", "round_start"]
    assert update["events"][1]["data"] == {"round": 2}


def test_consensus_omits_round_start_when_converged() -> None:
    # τ reachable AND round ≥ 2 → converged → proceed to HITL, no next round.
    # Round 2 is required: consensus_node never converges on the opening round,
    # where confidence reflects certainty in isolation rather than peer agreement.
    update = consensus_node(_consensus_state(round_=2, confidence_threshold=0.4))  # type: ignore[arg-type]

    assert update["converged"] is True
    assert [e["type"] for e in update["events"]] == ["consensus_update"]


def test_consensus_never_converges_on_the_opening_round() -> None:
    # Same reachable τ as above, but on round 1 → deliberately NOT converged, so the
    # mesh always debates at least twice before it can agree.
    update = consensus_node(_consensus_state(round_=1, confidence_threshold=0.4))  # type: ignore[arg-type]

    assert update["converged"] is False
    assert [e["type"] for e in update["events"]] == ["consensus_update", "round_start"]


def test_consensus_omits_round_start_at_max_rounds() -> None:
    # Unreachable τ but already at the last round → no further round opens.
    update = consensus_node(
        _consensus_state(round_=3, max_rounds=3, confidence_threshold=2.0)  # type: ignore[arg-type]
    )

    assert update["round"] == 4
    assert [e["type"] for e in update["events"]] == ["consensus_update"]


# ── agent_turn_node brackets every path with agent_turn_start ─────────────────


def test_agent_turn_start_prepended_on_stub_path() -> None:
    runtime = _FakeRuntime(MeshContext())  # runner=None → stub
    update = agent_turn_node({"agent_id": "a", "round": 1, "contributions": []}, runtime)  # type: ignore[arg-type]

    types = [e["type"] for e in update["events"]]
    assert types == ["agent_turn_start", "contribution"]
    assert update["events"][0]["data"] == {"agent_id": "a", "round": 1}


def test_agent_turn_start_prepended_on_abstention_path() -> None:
    runtime = _FakeRuntime(MeshContext(runner=_RaisingRunner()))
    update = agent_turn_node({"agent_id": "a", "round": 2, "contributions": []}, runtime)  # type: ignore[arg-type]

    types = [e["type"] for e in update["events"]]
    assert types == ["agent_turn_start", "error"]
    assert update["events"][0]["data"] == {"agent_id": "a", "round": 2}
    # The contribution is a confidence-0 abstention so the round still completes.
    assert update["contributions"][0]["confidence"] == 0.0
