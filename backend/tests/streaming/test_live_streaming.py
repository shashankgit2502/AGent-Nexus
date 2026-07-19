"""Bug 5 acceptance: an agent's tool calls + reasoning stream LIVE (ARCH §24.4).

Drives the **real** ``build_collab_graph`` (async ``astream`` path) with a real
``create_deep_agent`` agent whose scripted model calls a work tool, then emits its
``ContributionOut``. We assert the run's event log contains the activity events
(``reasoning`` / ``tool_call`` / ``tool_result``) in trajectory order *before* the
``contribution`` — i.e. they were emitted as the turn ran, not projected post-hoc —
and that they appear exactly once (no double emission with the node update).
"""

from __future__ import annotations

from uuid import UUID, uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolCall
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.config import AgentConfig, Capabilities, InMemoryAgentRepository
from app.agents.factory import AgentFactory, ModelProvider
from app.agents.mesh import FactoryMeshRunner
from app.graph.build import build_collab_graph
from app.graph.context import MeshContext
from app.graph.state import initial_collab_state
from app.models_layer.resolver import AgentModelRef
from app.streaming.emitter import RunEventEmitter
from app.streaming.publisher import InProcessEventPublisher
from app.streaming.runner import stream_run
from app.streaming.store import InMemoryRunEventStore
from app.tools.registry import ToolRegistry
from tests.agents._fakes import ScriptedToolCallingModel

_LOOKUPS: list[str] = []


@tool
def lookup(query: str) -> str:
    """Look up a fact for the query."""
    _LOOKUPS.append(query)
    return f"fact about {query}"


class _OneModelProvider(ModelProvider):
    def __init__(self, model: BaseChatModel) -> None:
        self._model = model

    def resolve(self, ref: AgentModelRef, *, require_tools: bool = True) -> BaseChatModel:
        return self._model


def _agent() -> AgentConfig:
    return AgentConfig(
        id=uuid4(),
        org_id=uuid4(),
        team_id=uuid4(),
        name="Researcher",
        instructions="You research facts.",
        profile_id=uuid4(),
        capabilities=Capabilities(web_search=True),  # gets the `lookup` tool below
    )


def _runner(cfg: AgentConfig, model: ScriptedToolCallingModel) -> FactoryMeshRunner:
    registry = ToolRegistry()
    registry.register("web_search", lambda _cfg: [lookup])
    factory = AgentFactory(models=_OneModelProvider(model), tools=registry)
    return FactoryMeshRunner(factory=factory, repo=InMemoryAgentRepository([cfg]))


async def test_tool_calls_and_reasoning_stream_live_before_the_contribution() -> None:
    _LOOKUPS.clear()
    cfg = _agent()
    # Scripted ReAct trajectory: reason + call `lookup`, then emit ContributionOut.
    model = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="Let me look that up.",
                tool_calls=[ToolCall(name="lookup", args={"query": "pgvector"}, id="t1")],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="ContributionOut",
                        args={"content": "Use pgvector.", "confidence": 0.9, "critiques": []},
                        id="t2",
                    )
                ],
            ),
        ]
    )
    runner = _runner(cfg, model)
    graph = build_collab_graph(InMemorySaver())
    store = InMemoryRunEventStore()
    emitter = await RunEventEmitter.for_run(
        session_id="s", run_id="r", store=store, publisher=InProcessEventPublisher()
    )
    # The mesh node streams live through `emit`; same emitter the run streamer uses.
    # live_streaming=True opts into the token-by-token path this test exercises (the
    # default is non-streaming for tool-call correctness — see AGENT_LIVE_STREAMING).
    context = MeshContext(runner=runner, emit=emitter.emit, live_streaming=True)
    state = initial_collab_state(
        goal="choose a vector store", active_agent_ids=[str(cfg.id)], max_rounds=1
    )

    await stream_run(graph, graph_input=state, config={"configurable": {"thread_id": "live"}},
                     emitter=emitter, context=context)

    events = await store.replay("r")
    by_type: dict[str, list[dict]] = {}
    for e in events:
        by_type.setdefault(e["type"], []).append(e)

    # The agent actually ran its ReAct loop (the work tool fired).
    assert _LOOKUPS == ["pgvector"]

    # Activity events were emitted live — exactly once each (no post-hoc duplicate).
    assert len(by_type.get("tool_call", [])) == 1
    assert len(by_type.get("tool_result", [])) == 1
    assert by_type["tool_call"][0]["data"]["tool"] == "lookup"
    assert by_type["tool_call"][0]["data"]["args"] == {"query": "pgvector"}
    assert by_type["tool_result"][0]["data"]["tool"] == "lookup"
    assert "fact about pgvector" in str(by_type["tool_result"][0]["data"]["result"])
    assert any("look that up" in r["data"]["text"] for r in by_type.get("reasoning", []))

    # Live ordering by seq: turn opens → reasoning → tool_call → tool_result →
    # contribution. The contribution (round-cadenced) comes AFTER the live activity.
    seq = {t: by_type[t][0]["seq"] for t in by_type}
    assert seq["agent_turn_start"] < seq["tool_call"] < seq["tool_result"] < seq["contribution"]
    assert seq["reasoning"] < seq["contribution"]

    # The ContributionOut exit tool never surfaces as a phantom tool event (§6).
    assert all(e["data"].get("tool") != "ContributionOut" for e in by_type.get("tool_call", []))
