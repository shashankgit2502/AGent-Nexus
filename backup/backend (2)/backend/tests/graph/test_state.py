"""Unit tests for CollabState — the blackboard reducers (ARCHITECTURE.md §6).

The additive reducer on `contributions`/`critiques`/`events` is the load-bearing
detail that lets parallel `Send()` agents write without clobbering. We assert it
directly with a tiny two-node parallel graph so the contract is pinned
independent of the full collaboration graph.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.graph.state import (
    Contribution,
    initial_collab_state,
    latest_round_contributions,
    make_event,
)


def test_initial_collab_state_is_fully_populated() -> None:
    state = initial_collab_state(goal="ship it", active_agent_ids=["a", "b"])

    # Every channel present (LangGraph requires the full schema on first invoke).
    assert state["goal"] == "ship it"
    assert state["active_agent_ids"] == ["a", "b"]
    assert state["round"] == 0
    assert state["max_rounds"] == 3
    # τ is the locked 0.85 (ARCH §8 / §8.1, CLAUDE §3). It was briefly 0.95 to
    # compensate for inflated self-scores; once the score became peer-weighted
    # rather than pure self-report, that compensation was removed.
    assert state["confidence_threshold"] == 0.85
    assert state["status"] == "init"
    assert state["contributions"] == []
    assert state["events"] == []
    assert state["hitl_enabled"] is False


def test_make_event_shape() -> None:
    event = make_event("contribution", agent_id="a", round=1)
    assert event == {"type": "contribution", "data": {"agent_id": "a", "round": 1}}


def test_latest_round_contributions_filters_by_round() -> None:
    state = initial_collab_state(goal="g", active_agent_ids=["a"])
    state["round"] = 2
    state["contributions"] = [
        Contribution(agent_id="a", round=1, content="old", confidence=0.5, tool_calls=[]),
        Contribution(agent_id="a", round=2, content="new", confidence=0.9, tool_calls=[]),
    ]
    latest = latest_round_contributions(state)
    assert [c["content"] for c in latest] == ["new"]


def test_additive_reducer_merges_parallel_writes() -> None:
    """Two parallel Send() branches writing `contributions` must both survive."""

    def fan(state: Any) -> list[Send]:
        return [Send("worker", {"agent_id": aid, "round": 1}) for aid in ("a", "b")]

    def worker(payload: Any) -> dict[str, Any]:
        c = Contribution(
            agent_id=payload["agent_id"],
            round=payload["round"],
            content=f"by {payload['agent_id']}",
            confidence=0.8,
            tool_calls=[],
        )
        return {"contributions": [c]}

    def join(state: Any) -> dict[str, Any]:
        return {}

    from app.graph.state import CollabState

    g: StateGraph = StateGraph(CollabState)
    g.add_node("worker", worker)
    g.add_node("join", join)
    g.add_conditional_edges(START, fan, ["worker"])
    g.add_edge("worker", "join")
    g.add_edge("join", END)
    app = g.compile(checkpointer=InMemorySaver())

    out = app.invoke(
        initial_collab_state(goal="g", active_agent_ids=["a", "b"]),
        {"configurable": {"thread_id": "merge-test"}},
    )

    authors = sorted(c["agent_id"] for c in out["contributions"])
    assert authors == ["a", "b"]  # neither parallel write clobbered the other
