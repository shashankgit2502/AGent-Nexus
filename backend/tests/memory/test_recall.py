"""Step-7 memory acceptance — an agent recalls a prior-session memory (ARCH §10.1).

"Done when … an agent recalls a prior-session memory." We persist a memory the way
a prior run would (via :class:`MemoryService`, the same namespaced store), then
build a **fresh** agent (a new "session") through the real ``AgentFactory`` and run
a turn. deepagents' ``MemoryMiddleware`` loads ``/memories/AGENTS.md`` from the
store into the agent's prompt; a recording model captures the messages it received,
and we assert the prior memory is present — i.e. it was recalled across sessions.

This is the genuine recall path (real factory, real deepagents memory, real store),
not a mock — only the chat model is scripted so the test runs offline.
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
from app.memory.service import MemoryService
from app.tools.registry import ToolRegistry
from tests.agents._fakes import RecordingModelProvider

_FACT = "The user prefers pgvector over FAISS for retrieval."


class _RecordingModel(BaseChatModel):
    """Captures every prompt it receives, then returns a scripted ContributionOut."""

    responses: list[BaseMessage] = []
    cursor: int = 0
    seen_prompts: list[str] = []

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> _RecordingModel:
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
        return "recording"


def test_agent_recalls_a_prior_session_memory() -> None:
    store = InMemoryStore()
    org, team, agent = uuid4(), uuid4(), uuid4()

    # ── "Session 1": a prior run persisted a memory to this agent's namespace. ──
    MemoryService(store).write(org_id=org, team_id=team, agent_id=agent, content=_FACT)

    # ── "Session 2": a fresh agent is spawned against the same store. ──
    model = _RecordingModel(
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
    factory = AgentFactory(models=RecordingModelProvider(model), tools=ToolRegistry(), store=store)
    cfg = AgentConfig(
        id=agent,
        org_id=org,
        team_id=team,
        name="Researcher",
        profile_id=uuid4(),
        capabilities=Capabilities(),
        memory_enabled=True,
    )
    agent_graph = factory.build(cfg)

    run_agent_turn(
        agent_graph, cfg, {"goal": "g", "round": 1, "contributions": [], "critiques": []}
    )

    # The prior-session memory was loaded into the prompt the new agent saw — recall.
    assert any("pgvector over FAISS" in prompt for prompt in model.seen_prompts)
