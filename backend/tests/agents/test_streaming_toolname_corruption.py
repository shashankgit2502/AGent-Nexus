"""Regression: streamed tool-call names corrupt on some providers → run non-streaming.

Root cause (R3, reproduced against NVIDIA NIM in isolation): an OpenAI-compatible
server (NIM, some vLLM builds) repeats the tool-call function ``name`` across
streamed delta chunks. LangChain accumulates streamed ``AIMessageChunk``s by
concatenating ``tool_call_chunks[i].name``, so two chunks each carrying
``web_search`` merge into ``web_searchweb_search`` — an invalid tool. Under
``tool_choice=required`` the agent then loops calling the non-existent tool and
never emits ``ContributionOut``, so the round yields nothing and the Workspace
freezes on "thinking" until the per-turn timeout abstains.

Fix: run the mesh turn **non-streaming** by default (``AGENT_LIVE_STREAMING=False``).
``ainvoke`` parses the whole response once, so the name is never corrupted; the
same trajectory events are projected post-hoc. ``test_*`` below lock both halves:
the upstream corruption mechanism (so we notice if it ever changes) and that the
non-streaming runner path produces a real contribution.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, AIMessageChunk, ToolCall
from langchain_core.messages.tool import tool_call_chunk

from app.agents.config import AgentConfig, Capabilities
from app.agents.factory import AgentFactory, ModelProvider
from app.agents.mesh import FactoryMeshRunner
from app.agents.snapshot import InMemoryAgentRepository
from app.models_layer.resolver import AgentModelRef
from app.tools.registry import ToolRegistry
from tests.agents._fakes import ScriptedToolCallingModel


def test_streamed_repeated_toolname_chunks_concatenate_into_an_invalid_name() -> None:
    """The upstream mechanism: a name repeated across stream chunks doubles on merge.

    This is exactly what NIM streaming triggers; it is why streaming the mesh turn
    is unsafe and the default is non-streaming.
    """
    c1 = AIMessageChunk(
        content="", tool_call_chunks=[tool_call_chunk(name="web_search", args="", id="t1", index=0)]
    )
    c2 = AIMessageChunk(
        content="",
        tool_call_chunks=[tool_call_chunk(name="web_search", args='{"q":"x"}', id=None, index=0)],
    )
    merged = c1 + c2
    assert merged.tool_calls[0]["name"] == "web_searchweb_search"  # the bug, documented


class _OneModelProvider(ModelProvider):
    def __init__(self, model: Any) -> None:
        self._model = model

    def resolve(self, ref: AgentModelRef, *, require_tools: bool = True) -> Any:
        return self._model


def _agent() -> AgentConfig:
    return AgentConfig(
        id=uuid4(),
        org_id=uuid4(),
        team_id=uuid4(),
        name="Researcher",
        instructions="You research facts.",
        profile_id=uuid4(),
        capabilities=Capabilities(web_search=True),
    )


async def test_non_streaming_turn_produces_a_real_contribution() -> None:
    """``arun(live=False)`` runs the agent non-streaming → a scorable contribution.

    The non-streaming path (the default) calls ``ainvoke``, which never streams
    tool-call name chunks, so the agent's exit tool fires and the turn yields a
    contribution instead of looping on a corrupted tool name.
    """
    cfg = _agent()
    model = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="ContributionOut",
                        args={"content": "KPMG India: assess audit quality.", "confidence": 0.8,
                              "critiques": []},
                        id="t1",
                    )
                ],
            )
        ]
    )
    registry = ToolRegistry()
    registry.register("web_search", lambda _cfg: [])
    factory = AgentFactory(models=_OneModelProvider(model), tools=registry)
    runner = FactoryMeshRunner(factory=factory, repo=InMemoryAgentRepository([cfg]))

    async def _noop_emit(_e: Any) -> None:
        return None

    update = await runner.arun(str(cfg.id), {"round": 1, "contributions": []}, emit=_noop_emit,
                               live=False)

    contributions = update["contributions"]
    assert len(contributions) == 1
    assert contributions[0]["confidence"] == 0.8
    assert contributions[0]["content"] == "KPMG India: assess audit quality."
    # A real contribution event is projected post-hoc (no streaming required).
    assert any(e["type"] == "contribution" for e in update["events"])
