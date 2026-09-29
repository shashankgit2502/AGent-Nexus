"""Slice-0 unit tests: agent-turn → ordered AG-UI events (ARCH §24.4 / §24.6).

These lock the **round-cadenced, post-hoc** projection of one agent's ReAct
trajectory into AG-UI events (CLAUDE.md §3 locked decision): reasoning / tool calls
/ tool results are derived from the completed turn's messages, in order, and the
``ContributionOut`` structured-output exit tool never leaks into the transparency
stream (§6). The contribution carries the proposal as a §24.6 content block, and
each peer critique becomes a ``critique`` event.

No model/network: messages are hand-built, and the contribution mapping is exercised
directly via ``_to_blackboard_update`` with a real ``ContributionOut`` result.
"""

from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage

from app.agents.config import AgentConfig, Capabilities
from app.agents.contribution import ContributionOut, CritiqueOut
from app.agents.runtime import _to_blackboard_update, turn_events


def _cfg() -> AgentConfig:
    return AgentConfig(
        id=uuid4(),
        org_id=uuid4(),
        team_id=uuid4(),
        name="Researcher",
        instructions="You research facts.",
        profile_id=uuid4(),
        capabilities=Capabilities(),
    )


def test_turn_events_orders_reasoning_tool_call_tool_result_and_excludes_exit_tool() -> None:
    messages = [
        HumanMessage(content="solve it"),
        AIMessage(
            content="I should look this up.",
            tool_calls=[ToolCall(name="lookup", args={"q": "x"}, id="c1")],
        ),
        ToolMessage(content="found: 42", name="lookup", tool_call_id="c1"),
        # The structured-output exit: an AI tool call + its ToolMessage — both must
        # be filtered from the transparency events (§6).
        AIMessage(
            content="",
            tool_calls=[ToolCall(name="ContributionOut", args={"content": "x"}, id="c2")],
        ),
        ToolMessage(
            content="Returning structured response", name="ContributionOut", tool_call_id="c2"
        ),
    ]

    events = turn_events(messages, agent_id="agent-1", current_round=2)

    assert [e["type"] for e in events] == ["reasoning", "tool_call", "tool_result"]
    assert events[0]["data"] == {
        "agent_id": "agent-1",
        "round": 2,
        "text": "I should look this up.",
    }
    assert events[1]["data"] == {
        "agent_id": "agent-1",
        "round": 2,
        "tool": "lookup",
        "args": {"q": "x"},
    }
    assert events[2]["data"] == {
        "agent_id": "agent-1",
        "round": 2,
        "tool": "lookup",
        "result": "found: 42",
    }


def test_to_blackboard_update_emits_contribution_content_blocks_then_critiques() -> None:
    cfg = _cfg()
    result = {
        "structured_response": ContributionOut(
            content="Use pgvector.",
            confidence=0.8,
            critiques=[CritiqueOut(target_agent="peer-7", severity="major", content="won't scale")],
        ),
        "messages": [
            AIMessage(content="", tool_calls=[ToolCall(name="ContributionOut", args={}, id="c1")]),
        ],
    }

    update = _to_blackboard_update(
        result, cfg=cfg, current_round=3, blackboard={"round": 3, "contributions": []}
    )

    types = [e["type"] for e in update["events"]]
    assert types == ["contribution", "critique"]

    contribution = update["events"][0]["data"]
    assert contribution["agent_id"] == str(cfg.id)
    assert contribution["round"] == 3
    assert contribution["confidence"] == 0.8
    assert contribution["content_blocks"] == [{"type": "text", "text": "Use pgvector."}]

    critique = update["events"][1]["data"]
    assert critique == {
        "sender": str(cfg.id),
        "target": "peer-7",
        "round": 3,
        "severity": "major",
        "content": "won't scale",
    }
