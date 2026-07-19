"""Post-run memory consolidation tests (ARCH §10.2 / §25.3, Item 3 M2).

The write trigger that was missing (Item 3 RCA): after a run, each memory-enabled
agent's contributions are distilled by the cheap model into one durable episodic
``experience`` record and the agent's ``/memories/AGENTS.md`` recall rollup is
refreshed — so the next session recalls it. All offline: a scripted model stands in
for the summariser, over the real ``InMemoryStore`` + ``MemoryItemStore`` (R2).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolCall
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.store.memory import InMemoryStore

from app.agents.config import AgentConfig, Capabilities
from app.agents.factory import AgentFactory
from app.agents.runtime import run_agent_turn
from app.graph.nodes.consolidation import consolidation_node
from app.memory.consolidation import MemoryConsolidator, render_consolidation_messages
from app.memory.items import MemoryItemStore
from app.memory.service import MemoryService
from app.tools.registry import ToolRegistry
from tests.agents._fakes import RecordingModelProvider


class _ScriptedTextModel(BaseChatModel):
    """Returns scripted text answers in order and records the prompts it saw."""

    answers: list[str] = []
    cursor: int = 0
    seen: list[str] = []

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen.append("\n".join(str(getattr(m, "content", "")) for m in messages))
        text = self.answers[self.cursor]
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    @property
    def _llm_type(self) -> str:
        return "scripted-text"


def _cfg(*, team: Any, memory: bool, name: str = "Researcher") -> AgentConfig:
    return AgentConfig(
        id=uuid4(),
        org_id=uuid4(),
        team_id=team,
        name=name,
        profile_id=uuid4(),
        capabilities=Capabilities(),
        memory_enabled=memory,
    )


def _contrib(agent_id: str, *, content: str, confidence: float, rnd: int = 1) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "round": rnd,
        "content": content,
        "confidence": confidence,
        "tool_calls": [],
    }


def _state(*, goal: str, active: list[str], contributions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"goal": goal, "active_agent_ids": active, "contributions": contributions}


def _consolidator(
    store: InMemoryStore, configs: Sequence[AgentConfig], answers: list[str]
) -> MemoryConsolidator:
    return MemoryConsolidator(
        configs=tuple(configs),
        items=MemoryItemStore(store),
        service=MemoryService(store),
        model=_ScriptedTextModel(answers=answers),
    )


def test_render_messages_carry_goal_and_contributions() -> None:
    msgs = render_consolidation_messages(
        agent_name="Researcher",
        goal="evaluate vector DBs",
        contributions=[_contrib("a", content="pgvector wins on ops", confidence=0.8)],
    )
    blob = "\n".join(str(m.content) for m in msgs)
    assert "evaluate vector DBs" in blob
    assert "pgvector wins on ops" in blob


def test_consolidate_writes_one_experience_for_memory_agent_only() -> None:
    store = InMemoryStore()
    team = uuid4()
    mem = _cfg(team=team, memory=True, name="Mem")
    plain = _cfg(team=team, memory=False, name="Plain")
    con = _consolidator(store, [mem, plain], answers=["I concluded pgvector fits best."])

    written = con.consolidate_run(
        _state(
            goal="g",
            active=[str(mem.id), str(plain.id)],
            contributions=[
                _contrib(str(mem.id), content="pgvector", confidence=0.8),
                _contrib(str(plain.id), content="faiss", confidence=0.9),
            ],
        )
    )

    assert len(written) == 1
    assert written[0].kind == "experience"
    assert written[0].content == "I concluded pgvector fits best."
    # Only the memory-enabled agent has a record.
    reader = MemoryItemStore(store)
    assert len(reader.list_items(org_id=mem.org_id, team_id=team, agent_id=mem.id)) == 1
    assert reader.list_items(org_id=plain.org_id, team_id=team, agent_id=plain.id) == []


def test_consolidate_skips_agent_with_no_real_contributions() -> None:
    store = InMemoryStore()
    team = uuid4()
    mem = _cfg(team=team, memory=True)
    model = _ScriptedTextModel(answers=[])  # must NOT be called
    con = MemoryConsolidator(
        configs=(mem,), items=MemoryItemStore(store), service=MemoryService(store), model=model
    )

    written = con.consolidate_run(
        _state(
            goal="g",
            active=[str(mem.id)],
            # Only a confidence-0 abstention → nothing worth remembering.
            contributions=[_contrib(str(mem.id), content="[abstained]", confidence=0.0)],
        )
    )

    assert written == []
    assert model.cursor == 0  # the model was never invoked
    assert MemoryItemStore(store).list_items(org_id=mem.org_id, team_id=team, agent_id=mem.id) == []


def test_none_response_skips_write() -> None:
    store = InMemoryStore()
    team = uuid4()
    mem = _cfg(team=team, memory=True)
    con = _consolidator(store, [mem], answers=["NONE"])

    written = con.consolidate_run(
        _state(
            goal="g",
            active=[str(mem.id)],
            contributions=[_contrib(str(mem.id), content="something", confidence=0.7)],
        )
    )

    assert written == []
    assert MemoryItemStore(store).list_items(org_id=mem.org_id, team_id=team, agent_id=mem.id) == []


def test_consolidate_refreshes_recall_rollup() -> None:
    store = InMemoryStore()
    team = uuid4()
    mem = _cfg(team=team, memory=True)
    con = _consolidator(store, [mem], answers=["I prefer pgvector for ops simplicity."])

    con.consolidate_run(
        _state(
            goal="g",
            active=[str(mem.id)],
            contributions=[_contrib(str(mem.id), content="pgvector", confidence=0.8)],
        )
    )

    rollup = MemoryService(store).read(org_id=mem.org_id, team_id=team, agent_id=mem.id)
    assert rollup is not None
    assert "pgvector for ops simplicity" in rollup


def test_node_no_context_is_a_noop() -> None:
    class _FakeRuntime:
        context = None

    assert consolidation_node({"goal": "g"}, _FakeRuntime()) == {}  # type: ignore[arg-type]


def test_consolidated_memory_is_recalled_by_a_fresh_agent() -> None:
    """End-to-end closure: consolidation writes → a fresh agent recalls it (§10.1)."""
    store = InMemoryStore()
    team = uuid4()
    mem = _cfg(team=team, memory=True)
    fact = "I learned the team favours pgvector over FAISS for retrieval."
    _consolidator(store, [mem], answers=[fact]).consolidate_run(
        _state(
            goal="vector db",
            active=[str(mem.id)],
            contributions=[_contrib(str(mem.id), content="pgvector", confidence=0.8)],
        )
    )

    # A fresh agent (new "session") spawned against the same store should see the
    # consolidated memory loaded into its prompt by deepagents' MemoryMiddleware.
    recorder = _RecordingAgentModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="ContributionOut",
                        args={"content": "noted", "confidence": 0.5, "critiques": []},
                        id="c1",
                    )
                ],
            )
        ]
    )
    factory = AgentFactory(
        models=RecordingModelProvider(recorder), tools=ToolRegistry(), store=store
    )
    agent_graph = factory.build(mem)
    run_agent_turn(
        agent_graph, mem, {"goal": "g", "round": 1, "contributions": [], "critiques": []}
    )

    assert any("pgvector over FAISS" in seen for seen in recorder.seen_prompts)


class _RecordingAgentModel(BaseChatModel):
    """Captures prompts, returns a scripted ContributionOut tool call."""

    responses: list[BaseMessage] = []
    cursor: int = 0
    seen_prompts: list[str] = []

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> _RecordingAgentModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen_prompts.append("\n".join(str(getattr(m, "content", "")) for m in messages))
        message = self.responses[self.cursor]
        self.cursor += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "recording-agent"
