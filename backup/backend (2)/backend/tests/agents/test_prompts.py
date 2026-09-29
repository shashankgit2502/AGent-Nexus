"""Unit tests for prompt rendering (ARCH §22.2)."""

from __future__ import annotations

from uuid import uuid4

from app.agents.config import AgentConfig
from app.agents.prompts import render_persona_prompt, render_round_message


def _agent(instructions: str = "") -> AgentConfig:
    return AgentConfig(
        id=uuid4(),
        org_id=uuid4(),
        team_id=uuid4(),
        name="Researcher",
        profile_id=uuid4(),
        instructions=instructions,
    )


def test_persona_prompt_includes_instructions_and_output_contract() -> None:
    prompt = render_persona_prompt(_agent("You are a market analyst."))
    assert "You are a market analyst." in prompt
    assert "ContributionOut" in prompt
    assert "confidence" in prompt


def test_persona_prompt_falls_back_to_name_when_no_instructions() -> None:
    assert "Researcher" in render_persona_prompt(_agent(""))


def test_persona_prompt_mentions_knowledge_tool_only_when_attached() -> None:
    """Bug 1 / §10.5.2 #4: the model must be told it has ``search_knowledge`` so it
    actually calls it — but only when the tool is genuinely attached, never on the
    config flag alone (advertising an absent tool invites hallucinated tool calls)."""
    cfg = _agent("analyst")
    with_tool = render_persona_prompt(cfg, has_knowledge_tool=True)
    assert "search_knowledge" in with_tool

    # Default + explicit-False must NOT mention the tool.
    assert "search_knowledge" not in render_persona_prompt(cfg)
    assert "search_knowledge" not in render_persona_prompt(cfg, has_knowledge_tool=False)


def test_persona_prompt_mentions_attachments_tool_only_when_attached() -> None:
    """Bug 2 / §8.5.3: the conversation-attachment tool is advertised only when it is
    actually attached for the turn (same never-advertise-an-absent-tool guard)."""
    cfg = _agent("analyst")
    assert "search_uploaded_files" in render_persona_prompt(cfg, has_attachments_tool=True)
    assert "search_uploaded_files" not in render_persona_prompt(cfg)
    assert "search_uploaded_files" not in render_persona_prompt(cfg, has_attachments_tool=False)


def test_round_message_includes_goal_framing_and_previous_round_contributions() -> None:
    cfg = _agent("analyst")
    self_id = str(cfg.id)
    # Realistic round-2 fan-out snapshot: only round-1 contributions exist; round-2
    # ones are being produced in parallel this super-step (ARCH §23.4).
    blackboard = {
        "goal": "pick a database",
        "success_criteria": ["must scale"],
        "agent_task_framing": {self_id: "focus on cost"},
        "round": 2,
        "contributions": [
            {
                "agent_id": "peer-x",
                "round": 1,
                "content": "use pgvector",
                "confidence": 0.7,
                "tool_calls": [],
            },
        ],
        "critiques": [
            {
                "from_agent": "peer-x",
                "target_agent": self_id,
                "round": 1,
                "content": "too costly",
                "severity": "major",
            },
        ],
    }
    message = render_round_message(cfg, blackboard)
    assert "pick a database" in message
    assert "must scale" in message
    assert "focus on cost" in message
    assert "use pgvector" in message  # previous-round peer contribution is surfaced
    assert "too costly" in message  # critique aimed at this agent


def test_round_message_surfaces_previous_round_not_in_flight_round() -> None:
    """Regression (R3): round-N rendering must show round N-1, not the empty N.

    Root cause: ``render_round_message`` previously filtered to the *current*
    round, but during a round-N ``Send()`` fan-out the round-N contributions do
    not exist yet — so peers' round-(N-1) work was hidden and every round-≥2 agent
    was told "opening round", blinding the mesh to prior contributions.
    """
    cfg = _agent("analyst")
    blackboard = {
        "goal": "g",
        "round": 3,
        "contributions": [
            # round 1 (stale) must NOT show; round 2 (previous) MUST show.
            {
                "agent_id": "p",
                "round": 1,
                "content": "ROUND-ONE",
                "confidence": 0.5,
                "tool_calls": [],
            },
            {
                "agent_id": "p",
                "round": 2,
                "content": "ROUND-TWO",
                "confidence": 0.8,
                "tool_calls": [],
            },
        ],
        "critiques": [],
    }
    message = render_round_message(cfg, blackboard)
    assert "ROUND-TWO" in message  # the immediately-preceding round
    assert "ROUND-ONE" not in message  # older rounds are not re-surfaced
    assert "opening round" not in message  # we are NOT blind in round 3


def test_round_message_handles_opening_round_with_no_contributions() -> None:
    cfg = _agent("analyst")
    blackboard = {"goal": "g", "round": 1, "contributions": [], "critiques": []}
    assert "opening round" in render_round_message(cfg, blackboard)
