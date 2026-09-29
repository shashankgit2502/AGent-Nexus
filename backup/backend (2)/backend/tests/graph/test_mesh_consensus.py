"""Step-5 acceptance: mesh round + consensus (BUILD_PLAYBOOK Step 5 / ARCH §7–§8).

"Done when: a 3-agent team runs multiple rounds and terminates by both rules;
ranking is correct."

These tests drive the **full** ``build_collab_graph`` with **real**
``create_deep_agent`` agents (built by the factory, Step 4) whose models are
scripted tool-calling stand-ins (offline, deterministic). The mesh runner is
injected via LangGraph runtime context (``MeshContext``). They exercise:

* termination by confidence (``mean ≥ τ``) — converges in round 2,
* termination by ``max_rounds`` when τ is unreachable,
* the confidence-weighted ranking order (ARCH §8),
* graceful abstention when one agent fails (ARCH §21.5),
* the ``(agent_id, round)`` idempotency guard (ARCH §22.5).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolCall
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.config import AgentConfig, Capabilities, InMemoryAgentRepository
from app.agents.factory import AgentFactory, ModelProvider
from app.agents.mesh import FactoryMeshRunner
from app.graph.build import build_collab_graph
from app.graph.context import MeshContext
from app.graph.nodes.agent_turn import aagent_turn_node, agent_turn_node
from app.graph.state import initial_collab_state
from app.models_layer.resolver import AgentModelRef
from app.tools.registry import ToolRegistry
from tests.agents._fakes import ScriptedToolCallingModel

# ── scripted-model helpers ───────────────────────────────────────────────────


def _contribution(content: str, confidence: float) -> AIMessage:
    """An AI message that emits a ContributionOut (ends the ReAct loop)."""
    return AIMessage(
        content="",
        tool_calls=[
            ToolCall(
                name="ContributionOut",
                args={"content": content, "confidence": confidence, "critiques": []},
                id=f"call-{content}",
            )
        ],
    )


def _model(*turns: tuple[str, float]) -> ScriptedToolCallingModel:
    """A model that returns one ContributionOut per round, in order."""
    return ScriptedToolCallingModel(responses=[_contribution(c, conf) for c, conf in turns])


class _MappingModelProvider(ModelProvider):
    """Returns a distinct scripted model per agent, keyed by ``profile_id``."""

    def __init__(self, by_profile: dict[UUID, BaseChatModel]) -> None:
        self._by_profile = by_profile

    def resolve(self, ref: AgentModelRef, *, require_tools: bool = True) -> BaseChatModel:
        return self._by_profile[ref.profile_id]


def _agent(name: str) -> AgentConfig:
    return AgentConfig(
        id=uuid4(),
        org_id=uuid4(),
        team_id=uuid4(),
        name=name,
        instructions=f"You are {name}.",
        profile_id=uuid4(),
        capabilities=Capabilities(),  # no tools needed; ranking is what we assert
    )


def _runner(agents_to_models: dict[AgentConfig, BaseChatModel]) -> FactoryMeshRunner:
    repo = InMemoryAgentRepository(list(agents_to_models))
    provider = _MappingModelProvider({a.profile_id: m for a, m in agents_to_models.items()})
    factory = AgentFactory(models=provider, tools=ToolRegistry())
    return FactoryMeshRunner(factory=factory, repo=repo)


def _roster(*agents: AgentConfig) -> list[str]:
    return [str(a.id) for a in agents]


# ── acceptance: termination by both rules + ranking ──────────────────────────


def test_three_agents_converge_by_confidence_with_correct_ranking() -> None:
    a, b, c = _agent("A"), _agent("B"), _agent("C")
    # Round 1 mean = 0.60 (< τ 0.85) → debate again. Round 2 mean ≈ 0.92 (≥ τ) → converge.
    runner = _runner(
        {
            a: _model(("A-r1", 0.50), ("A-r2", 0.90)),
            b: _model(("B-r1", 0.60), ("B-r2", 0.92)),
            c: _model(("C-r1", 0.70), ("C-r2", 0.95)),
        }
    )
    app = build_collab_graph(InMemorySaver())
    state = initial_collab_state(
        goal="choose a vector store",
        active_agent_ids=_roster(a, b, c),
        confidence_threshold=0.85,
        max_rounds=3,
    )

    out = app.invoke(
        state, {"configurable": {"thread_id": "conv"}}, context=MeshContext(runner=runner)
    )

    assert out["status"] == "done"
    assert out["converged"] is True
    # Multiple rounds actually ran (the mesh, not a single pass).
    assert {ct["round"] for ct in out["contributions"]} == {1, 2}
    assert len(out["contributions"]) == 6  # 3 agents × 2 rounds

    # Confidence-weighted ranking of the FINAL round, best first (ARCH §8).
    assert out["consensus_ranking"] == [f"{c.id}:2", f"{b.id}:2", f"{a.id}:2"]
    # Synthesizer picks the top-ranked contribution's content.
    assert out["final_output"] == "C-r2"


def test_three_agents_terminate_by_max_rounds_when_never_converging() -> None:
    a, b, c = _agent("A"), _agent("B"), _agent("C")
    runner = _runner(
        {
            a: _model(("A-r1", 0.30), ("A-r2", 0.40)),
            b: _model(("B-r1", 0.30), ("B-r2", 0.40)),
            c: _model(("C-r1", 0.30), ("C-r2", 0.40)),
        }
    )
    app = build_collab_graph(InMemorySaver())
    state = initial_collab_state(
        goal="hard problem",
        active_agent_ids=_roster(a, b, c),
        confidence_threshold=2.0,  # unreachable → termination is by max_rounds only
        max_rounds=2,
    )

    out = app.invoke(
        state, {"configurable": {"thread_id": "maxr"}}, context=MeshContext(runner=runner)
    )

    assert out["status"] == "done"
    assert out["converged"] is False
    # Bug 4: max_rounds=N runs exactly N debate rounds (locked §3 "loop until rounds ≥ N").
    assert {ct["round"] for ct in out["contributions"]} == {1, 2}
    assert len(out["contributions"]) == 6


# ── resilience: a failing agent abstains, the round still completes (§21.5) ───


def test_failed_agent_abstains_and_round_completes() -> None:
    a, b, c = _agent("A"), _agent("B"), _agent("C")
    # Agent B returns a plain message (no ContributionOut) → run_agent_turn raises
    # → the node records a confidence-0 abstention rather than stalling the round.
    runner = _runner(
        {
            a: _model(("A-r1", 0.50)),
            b: ScriptedToolCallingModel(responses=[AIMessage(content="I cannot answer.")]),
            c: _model(("C-r1", 0.70)),
        }
    )
    app = build_collab_graph(InMemorySaver())
    state = initial_collab_state(
        goal="g",
        active_agent_ids=_roster(a, b, c),
        confidence_threshold=2.0,
        max_rounds=1,  # single round is enough to observe the abstention
    )

    out = app.invoke(
        state, {"configurable": {"thread_id": "abst"}}, context=MeshContext(runner=runner)
    )

    assert out["status"] == "done"
    # The round produced all three agents' slots — B's is a confidence-0 abstention.
    by_agent = {ct["agent_id"]: ct for ct in out["contributions"]}
    assert by_agent[str(b.id)]["confidence"] == 0.0
    assert "[abstained]" in by_agent[str(b.id)]["content"]
    assert by_agent[str(a.id)]["confidence"] == 0.50  # peers unaffected
    assert by_agent[str(c.id)]["confidence"] == 0.70
    # The failure is surfaced as an AG-UI error event, not silently swallowed (R3).
    errors = [e for e in out["events"] if e["type"] == "error"]
    assert any(e["data"]["agent_id"] == str(b.id) for e in errors)


# ── idempotency guard (§22.5) ────────────────────────────────────────────────


class _FakeRuntime:
    """Minimal stand-in exposing only ``.context`` (what the node reads)."""

    def __init__(self, context: MeshContext) -> None:
        self.context = context


class _ExplodingRunner:
    """A runner that fails if called — proves the idempotency guard short-circuits."""

    def run(self, agent_id: str, blackboard: Any) -> dict[str, Any]:  # noqa: ANN401
        raise AssertionError("runner must not be invoked when the turn is idempotent")


def test_agent_turn_is_idempotent_for_same_agent_and_round() -> None:
    payload = {
        "agent_id": "agent-1",
        "round": 2,
        "contributions": [
            {
                "agent_id": "agent-1",
                "round": 2,
                "content": "x",
                "confidence": 0.9,
                "tool_calls": [],
            },
        ],
    }
    runtime = _FakeRuntime(MeshContext(runner=_ExplodingRunner()))

    update = agent_turn_node(payload, runtime)  # type: ignore[arg-type]

    assert update == {}  # no double-append; runner never invoked


class _HangingRunner:
    """An async runner whose turn never returns in time — simulates a slow/dead model."""

    def run(self, agent_id: str, blackboard: Any) -> dict[str, Any]:  # noqa: ANN401
        raise AssertionError("sync run not used")

    async def arun(  # noqa: ANN401
        self, agent_id: str, blackboard: Any, *, emit: Any, live: bool = True
    ) -> dict[str, Any]:
        await asyncio.sleep(5)  # far beyond the test's turn_timeout
        raise AssertionError("should have been cancelled by the per-turn timeout")


async def test_live_turn_abstains_on_per_turn_timeout() -> None:
    """A slow/unresponsive model (any provider) must abstain — not freeze the round.

    Provider-agnostic resilience (R3/R4): the live turn is bounded by
    ``MeshContext.turn_timeout_s``; exceeding it cancels the turn and records a
    confidence-0 abstention so the round still completes with the other agents.
    """
    emitted: list[str] = []

    async def _emit(e: dict[str, Any]) -> None:
        emitted.append(e["type"])

    runtime = _FakeRuntime(
        MeshContext(runner=_HangingRunner(), emit=_emit, turn_timeout_s=0.05)
    )
    update = await aagent_turn_node(
        {"agent_id": "a", "round": 1, "contributions": []}, runtime  # type: ignore[arg-type]
    )

    assert emitted == ["agent_turn_start"]  # the turn opened live, then timed out
    contribution = update["contributions"][0]
    assert contribution["confidence"] == 0.0
    assert "[abstained]" in contribution["content"]
    assert "no activity for" in contribution["content"]  # the reason is surfaced (R3)
    assert any(e["type"] == "error" for e in update["events"])


def test_agent_turn_stub_path_when_no_runner() -> None:
    """No runner in context → deterministic stub (foundation behaviour).

    The opening round sits below τ (Bug 4) so a Deep Collaborate run debates a second
    round; round 1 still emits just a contribution (no peers to build on yet).
    """
    payload = {"agent_id": "agent-1", "round": 1, "contributions": []}
    runtime = _FakeRuntime(MeshContext())  # runner=None

    update = agent_turn_node(payload, runtime)  # type: ignore[arg-type]

    assert update["contributions"][0]["content"].startswith("[stub]")
    assert update["contributions"][0]["confidence"] == pytest.approx(0.6)
    assert "responds_to" not in update["contributions"][0]  # opening round → no edges
    assert update.get("critiques", []) == []
