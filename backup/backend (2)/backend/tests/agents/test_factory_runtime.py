"""Step-4 acceptance + factory unit tests (ARCH §22.2 / BUILD_PLAYBOOK Step 4).

Acceptance ("Done when"): one real ReAct agent runs a turn — reads the blackboard,
**calls a tool**, and writes a contribution + confidence. We build a genuine
``create_deep_agent`` through the factory and drive its real ReAct loop with a
scripted tool-calling model (offline, deterministic), then map the result onto the
blackboard with ``run_agent_turn``.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolCall
from langchain_core.tools import tool
from langgraph.store.memory import InMemoryStore

from app.agents.config import AgentConfig, Capabilities
from app.agents.contribution import ContributionOut
from app.agents.factory import AgentBuildError, AgentFactory
from app.agents.runtime import (
    AgentTurnError,
    _to_blackboard_update,
    arun_agent_turn,
    make_structured_repair,
    run_agent_turn,
)
from app.skills.loader import SkillSource
from app.tools.registry import ToolRegistry
from tests.agents._fakes import RecordingModelProvider, ScriptedToolCallingModel

# A real, deterministic tool the agent must call (no infra needed).
_LOOKUP_CALLS: list[str] = []


@tool
def lookup(query: str) -> str:
    """Look up a fact for the given query."""
    _LOOKUP_CALLS.append(query)
    return f"fact about {query}"


def _factory(model: ScriptedToolCallingModel) -> tuple[AgentFactory, RecordingModelProvider]:
    provider = RecordingModelProvider(model)
    registry = ToolRegistry()
    registry.register("web_search", lambda cfg: [lookup])
    return AgentFactory(models=provider, tools=registry), provider


def _agent_cfg(**kw: object) -> AgentConfig:
    base: dict[str, object] = {
        "id": uuid4(),
        "org_id": uuid4(),
        "team_id": uuid4(),
        "name": "Researcher",
        "instructions": "You research facts.",
        "profile_id": uuid4(),
        "capabilities": Capabilities(web_search=True),
    }
    base.update(kw)
    return AgentConfig(**base)  # type: ignore[arg-type]


def test_one_real_agent_runs_a_turn_calls_tool_and_writes_contribution() -> None:
    _LOOKUP_CALLS.clear()
    cfg = _agent_cfg()
    self_id = str(cfg.id)

    # Scripted ReAct trajectory: (1) call the `lookup` tool, then (2) emit the
    # ContributionOut structured output (ToolStrategy ends the loop on this).
    model = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[ToolCall(name="lookup", args={"query": "pgvector"}, id="c1")],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="ContributionOut",
                        args={
                            "content": "Use pgvector for RAG.",
                            "confidence": 0.77,
                            "critiques": [],
                        },
                        id="c2",
                    )
                ],
            ),
        ]
    )
    factory, provider = _factory(model)
    agent = factory.build(cfg)

    blackboard = {
        "goal": "choose a vector store",
        "success_criteria": ["runs in our Postgres"],
        "agent_task_framing": {self_id: "weigh operational cost"},
        "round": 1,
        "contributions": [],
        "critiques": [],
    }
    update = run_agent_turn(agent, cfg, blackboard)

    # The agent actually invoked the real tool during its ReAct loop.
    assert _LOOKUP_CALLS == ["pgvector"]

    # It wrote exactly one contribution with content + confidence to the blackboard.
    assert len(update["contributions"]) == 1
    contribution = update["contributions"][0]
    assert contribution["agent_id"] == self_id
    assert contribution["round"] == 1
    assert contribution["content"] == "Use pgvector for RAG."
    assert contribution["confidence"] == 0.77
    assert {"name": "lookup", "args": {"query": "pgvector"}} in contribution["tool_calls"]

    # Regression (R3): the structured-output sentinel must NOT leak into the
    # transparency tool_calls — only real work tools belong there (§6).
    assert all(tc["name"] != "ContributionOut" for tc in contribution["tool_calls"])
    assert contribution["tool_calls"] == [{"name": "lookup", "args": {"query": "pgvector"}}]

    # And it emitted the ordered AG-UI trajectory for the turn (ARCH §24.4): the
    # work tool call, its result, then the contribution. The ContributionOut exit
    # tool never appears as a tool_call/tool_result (§6). agent_turn_start is added
    # by the node, not run_agent_turn, so it is absent here.
    assert [e["type"] for e in update["events"]] == ["tool_call", "tool_result", "contribution"]
    tool_call_event = next(e for e in update["events"] if e["type"] == "tool_call")
    assert tool_call_event["data"] == {
        "agent_id": self_id,
        "round": 1,
        "tool": "lookup",
        "args": {"query": "pgvector"},
    }
    # The contribution carries the proposal as a §24.6 text content block.
    contribution_event = next(e for e in update["events"] if e["type"] == "contribution")
    assert contribution_event["data"]["content_blocks"] == [
        {"type": "text", "text": "Use pgvector for RAG."}
    ]

    # The factory enforced the §9.3 tool-calling gate when resolving the model.
    assert provider.calls and provider.calls[0][1] is True


async def test_async_turn_maps_critiques_onto_blackboard() -> None:
    """arun_agent_turn produces the same shape and stamps critiques (§22.2)."""
    _LOOKUP_CALLS.clear()
    cfg = _agent_cfg()
    peer = "peer-7"
    model = ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="ContributionOut",
                        args={
                            "content": "Disagree: shard instead.",
                            "confidence": 0.6,
                            "critiques": [
                                {
                                    "target_agent": peer,
                                    "severity": "major",
                                    "content": "won't scale",
                                }
                            ],
                        },
                        id="c1",
                    )
                ],
            ),
        ]
    )
    factory, _ = _factory(model)
    agent = factory.build(cfg)
    update = await arun_agent_turn(
        agent, cfg, {"goal": "g", "round": 3, "contributions": [], "critiques": []}
    )

    assert update["contributions"][0]["confidence"] == 0.6
    critique = update["critiques"][0]
    assert critique["from_agent"] == str(cfg.id)
    assert critique["target_agent"] == peer
    assert critique["round"] == 3
    assert critique["severity"] == "major"


def test_factory_passes_tool_calling_gate_to_resolver() -> None:
    factory, provider = _factory(ScriptedToolCallingModel(responses=[]))
    factory.build(_agent_cfg(capabilities=Capabilities()))
    ref, require_tools = provider.calls[0]
    assert require_tools is True  # mesh agents must be tool-capable (§9.3)


def test_factory_binds_tool_strategy_not_native(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression (R3): structured output must be pinned to ``ToolStrategy``.

    Root cause of the field abstention ("Failed to parse structured output for tool
    'ContributionOut' … Expecting value: line 1 column 1 (char 0)"): a bare schema
    becomes ``AutoStrategy`` → the provider's *native* JSON mode for capable models,
    which parses empty assistant content as JSON and crashes the turn. The factory
    must wrap the schema in ``ToolStrategy`` so the typed result always arrives as a
    validated tool call. We capture the kwarg the factory hands to deepagents.
    """
    from langchain.agents.structured_output import ToolStrategy

    from app.agents import factory as factory_mod
    from app.agents.contribution import ContributionOut

    captured: dict[str, object] = {}

    def _spy_create_deep_agent(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()  # the built agent is never invoked in this test

    monkeypatch.setattr(factory_mod, "create_deep_agent", _spy_create_deep_agent)
    factory, _ = _factory(ScriptedToolCallingModel(responses=[]))
    factory.build(_agent_cfg(capabilities=Capabilities()))

    response_format = captured["response_format"]
    assert isinstance(response_format, ToolStrategy)
    assert response_format.schema is ContributionOut


@tool
def search_knowledge(query: str) -> str:
    """Fake team knowledge search (named to match the real RAG tool)."""
    return f"passages for {query}"


@tool
def search_uploaded_files(query: str) -> str:
    """Fake conversation-attachment search (named to match the real per-turn tool)."""
    return f"attachment passages for {query}"


def _capture_built_agent(
    monkeypatch: pytest.MonkeyPatch, factory: AgentFactory, cfg: AgentConfig
) -> dict[str, object]:
    """Build ``cfg`` but capture the kwargs handed to ``create_deep_agent``."""
    from app.agents import factory as factory_mod

    captured: dict[str, object] = {}

    def _spy(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory_mod, "create_deep_agent", _spy)
    factory.build(cfg)
    return captured


def test_rag_agent_gets_search_knowledge_tool_and_prompt_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug 1 (root cause): when the ``rag`` builder is registered, a rag-enabled agent
    is spawned WITH ``search_knowledge`` AND a system prompt that tells it to use it.

    This is the contract the composition root (``snapshot.build_mesh_context``) must
    satisfy by registering ``make_rag_tool_builder`` on the registry — the original
    bug spawned every agent through a *bare* ``ToolRegistry()``, so the tool (and the
    hint) were silently dropped and ingested knowledge was unreachable at runtime.
    """
    provider = RecordingModelProvider(ScriptedToolCallingModel(responses=[]))
    registry = ToolRegistry()
    registry.register("rag", lambda cfg: [search_knowledge])
    factory = AgentFactory(models=provider, tools=registry)

    cfg = _agent_cfg(capabilities=Capabilities(rag=True))
    captured = _capture_built_agent(monkeypatch, factory, cfg)

    tool_names = [t.name for t in captured["tools"]]  # type: ignore[attr-defined]
    assert "search_knowledge" in tool_names
    assert "search_knowledge" in captured["system_prompt"]  # type: ignore[operator]


def test_rag_agent_without_registered_builder_has_no_tool_or_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The buggy state, pinned: a bare registry (no ``rag`` builder) yields neither the
    tool nor the prompt hint — and the hint must never appear without the tool."""
    provider = RecordingModelProvider(ScriptedToolCallingModel(responses=[]))
    factory = AgentFactory(models=provider, tools=ToolRegistry())  # nothing registered

    cfg = _agent_cfg(capabilities=Capabilities(rag=True))
    captured = _capture_built_agent(monkeypatch, factory, cfg)

    assert "search_knowledge" not in [t.name for t in captured["tools"]]  # type: ignore[attr-defined]
    assert "search_knowledge" not in captured["system_prompt"]  # type: ignore[operator]


def test_extra_tools_appended_to_every_agent_and_drive_attachment_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug 2 / §8.5.3: the per-turn conversation-attachment tool is injected via
    ``extra_tools`` (independent of capabilities) and the prompt advertises it only
    because it is actually attached."""
    provider = RecordingModelProvider(ScriptedToolCallingModel(responses=[]))
    factory = AgentFactory(
        models=provider, tools=ToolRegistry(), extra_tools=(search_uploaded_files,)
    )

    cfg = _agent_cfg(capabilities=Capabilities())  # no RAG capability at all
    captured = _capture_built_agent(monkeypatch, factory, cfg)

    assert "search_uploaded_files" in [t.name for t in captured["tools"]]  # type: ignore[attr-defined]
    assert "search_uploaded_files" in captured["system_prompt"]  # type: ignore[operator]


def test_memory_enabled_without_store_fails_fast() -> None:
    factory, _ = _factory(ScriptedToolCallingModel(responses=[]))
    with pytest.raises(AgentBuildError, match="memory_enabled"):
        factory.build(_agent_cfg(memory_enabled=True))


def test_uploaded_skills_without_store_fail_fast() -> None:
    factory, _ = _factory(ScriptedToolCallingModel(responses=[]))
    cfg = _agent_cfg(
        skill_sources=(SkillSource(name="r", origin="uploaded", path="/skills/uploaded/r"),)
    )
    with pytest.raises(AgentBuildError, match="uploaded skills"):
        factory.build(cfg)


def _structured_only_model() -> ScriptedToolCallingModel:
    return ScriptedToolCallingModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    ToolCall(
                        name="ContributionOut",
                        args={"content": "ok", "confidence": 0.5, "critiques": []},
                        id="c1",
                    )
                ],
            )
        ]
    )


def test_memory_enabled_with_store_builds_and_runs() -> None:
    """The CompositeBackend + StoreBackend (/memories/) happy path (§10.1)."""
    provider = RecordingModelProvider(_structured_only_model())
    factory = AgentFactory(models=provider, tools=ToolRegistry(), store=InMemoryStore())
    cfg = _agent_cfg(capabilities=Capabilities(), memory_enabled=True)
    agent = factory.build(cfg)
    update = run_agent_turn(
        agent, cfg, {"goal": "g", "round": 1, "contributions": [], "critiques": []}
    )
    assert update["contributions"][0]["confidence"] == 0.5


# ── Structured-output repair fallback (R3: model ended without ContributionOut) ──


def test_model_for_resolves_with_tool_gate() -> None:
    """`model_for` shares the §9.3 gated resolution the built agent uses."""
    factory, provider = _factory(ScriptedToolCallingModel(responses=[]))
    factory.model_for(_agent_cfg())
    assert provider.calls[-1][1] is True


def test_repair_recovers_contribution_when_no_structured_response() -> None:
    """A turn that ended with plain text (no ContributionOut) is salvaged via the
    repair callable into a real typed contribution — not discarded (§21.5)."""
    cfg = _agent_cfg()
    self_id = str(cfg.id)
    recovered = ContributionOut(content="recovered proposal", confidence=0.62, critiques=[])
    result = {
        "messages": [AIMessage(content="here is my plain-text answer")],
        "structured_response": None,
    }
    update = _to_blackboard_update(
        result,
        cfg=cfg,
        current_round=1,
        blackboard={"round": 1, "contributions": []},
        repair=lambda _messages: recovered,
    )
    contribution = update["contributions"][0]
    assert contribution["agent_id"] == self_id
    assert contribution["content"] == "recovered proposal"
    assert contribution["confidence"] == 0.62


def test_abstains_when_no_structured_response_and_no_repair() -> None:
    """Behaviour preserved: without a repair, a structureless turn still raises
    (the node turns this into a confidence-0 abstention)."""
    with pytest.raises(AgentTurnError, match="no ContributionOut"):
        _to_blackboard_update(
            {"messages": [], "structured_response": None},
            cfg=_agent_cfg(),
            current_round=1,
            blackboard={"round": 1, "contributions": []},
        )


def test_abstains_when_repair_also_fails() -> None:
    with pytest.raises(AgentTurnError, match="no ContributionOut"):
        _to_blackboard_update(
            {"messages": [], "structured_response": None},
            cfg=_agent_cfg(),
            current_round=1,
            blackboard={"round": 1, "contributions": []},
            repair=lambda _messages: None,
        )


class _ScriptedExtractor:
    def __init__(self, out: object, *, boom: bool = False) -> None:
        self._out = out
        self._boom = boom

    def invoke(self, _messages: object) -> object:
        if self._boom:
            raise RuntimeError("provider blew up during repair")
        return self._out


class _RepairModel:
    """Minimal stand-in exposing only `with_structured_output` for the repair builder."""

    def __init__(self, out: object, *, boom: bool = False) -> None:
        self._extractor = _ScriptedExtractor(out, boom=boom)

    def with_structured_output(self, _schema: object) -> _ScriptedExtractor:
        return self._extractor


def test_make_structured_repair_returns_contribution_on_success() -> None:
    out = ContributionOut(content="x", confidence=0.5)
    repair = make_structured_repair(_RepairModel(out))  # type: ignore[arg-type]
    assert repair([]) == out


def test_make_structured_repair_swallows_failure_returns_none() -> None:
    """The repair is a fallback: if the salvage call raises, return None so the
    caller abstains gracefully rather than crashing the round."""
    repair = make_structured_repair(_RepairModel(None, boom=True))  # type: ignore[arg-type]
    assert repair([]) is None


def test_filesystem_base_skills_dir_builds_and_runs(tmp_path: Path) -> None:
    """The FilesystemBackend (base-skills) happy path with path containment (§26.4)."""
    provider = RecordingModelProvider(_structured_only_model())
    factory = AgentFactory(models=provider, tools=ToolRegistry(), base_skills_dir=tmp_path)
    cfg = _agent_cfg(capabilities=Capabilities())
    agent = factory.build(cfg)
    update = run_agent_turn(
        agent, cfg, {"goal": "g", "round": 1, "contributions": [], "critiques": []}
    )
    assert update["contributions"][0]["content"] == "ok"
