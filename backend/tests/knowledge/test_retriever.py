"""search_knowledge tool + RAG capability builder tests (ARCH §10.5.2/§10.5.4).

The tool's security guarantee is the *filter it binds into the retriever*. We
assert it wires exactly ``build_knowledge_filter``'s output and formats passages
with source attribution. End-to-end isolation against a real pgvector is in
``test_pgvector_integration.py``; here the store boundary is a recording double.
"""

from __future__ import annotations

from uuid import uuid4

from langchain_core.documents import Document

from app.agents.config import AgentConfig, Capabilities, KnowledgeConfig
from app.knowledge.metadata import build_conversation_filter, build_knowledge_filter
from app.knowledge.retriever import (
    make_conversation_tool,
    make_knowledge_tool,
    make_rag_tool_builder,
)
from app.tools.registry import ToolRegistry


class _FakeRetriever:
    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs

    def invoke(self, _query: str) -> list[Document]:
        return self.docs


class _ExplodingRetriever:
    """Stands in for a retriever whose embedding endpoint is misconfigured (404)."""

    def invoke(self, _query: str) -> list[Document]:
        raise RuntimeError("Function 'abc': Not found for account")


class _FakeStore:
    """Records the search_kwargs the tool binds; returns canned docs."""

    def __init__(self, docs: list[Document], *, retriever: object | None = None) -> None:
        self.docs = docs
        self.search_kwargs: dict | None = None
        self._retriever = retriever

    def as_retriever(self, *, search_kwargs: dict):  # noqa: ANN001, ANN201
        self.search_kwargs = search_kwargs
        return self._retriever or _FakeRetriever(self.docs)


def _cfg(**kw: object) -> AgentConfig:
    base: dict[str, object] = {
        "id": uuid4(),
        "org_id": uuid4(),
        "team_id": uuid4(),
        "name": "R",
        "profile_id": uuid4(),
    }
    base.update(kw)
    return AgentConfig(**base)  # type: ignore[arg-type]


def test_tool_binds_tenant_filter_and_k() -> None:
    cfg = _cfg()
    store = _FakeStore([])
    make_knowledge_tool(store, cfg=cfg, k=4)  # type: ignore[arg-type]
    assert store.search_kwargs is not None
    assert store.search_kwargs["k"] == 4
    assert store.search_kwargs["filter"] == build_knowledge_filter(
        org_id=cfg.org_id,
        team_id=cfg.team_id,
        agent_id=cfg.id,
        only_specified_sources=False,
        source_ids=(),
    )


def test_tool_honours_only_specified_sources() -> None:
    s1 = uuid4()
    cfg = _cfg(knowledge=KnowledgeConfig(only_specified_sources=True, source_ids=(s1,)))
    store = _FakeStore([])
    make_knowledge_tool(store, cfg=cfg)  # type: ignore[arg-type]
    assert {"source_id": {"$in": [str(s1)]}} in store.search_kwargs["filter"]["$and"]


def test_tool_formats_passages_with_source_attribution() -> None:
    docs = [
        Document(page_content="alpha", metadata={"source_id": "s1"}),
        Document(page_content="beta", metadata={"source_id": "s2"}),
    ]
    tool = make_knowledge_tool(_FakeStore(docs), cfg=_cfg())  # type: ignore[arg-type]
    out = tool.invoke({"query": "q"})
    assert "[s1] alpha" in out
    assert "[s2] beta" in out


def test_tool_degrades_gracefully_when_retrieval_fails() -> None:
    """A retrieval/embedding failure (e.g. a misconfigured embedding model 404) must
    NOT abort the agent turn — the tool returns an informative observation instead of
    raising, so the ReAct loop continues (Bug 5 root cause)."""
    store = _FakeStore([], retriever=_ExplodingRetriever())
    tool = make_knowledge_tool(store, cfg=_cfg())  # type: ignore[arg-type]
    out = tool.invoke({"query": "q"})
    assert "currently unavailable" in out
    assert "Not found for account" in out  # the real cause is surfaced, not hidden
    # And it never propagates as an exception (the turn keeps going).


def test_conversation_tool_degrades_gracefully_when_retrieval_fails() -> None:
    store = _FakeStore([], retriever=_ExplodingRetriever())
    tool = make_conversation_tool(store, org_id=uuid4(), conversation_id=uuid4())  # type: ignore[arg-type]
    out = tool.invoke({"query": "q"})
    assert "currently unavailable" in out


def test_tool_reports_no_results_cleanly() -> None:
    tool = make_knowledge_tool(_FakeStore([]), cfg=_cfg())  # type: ignore[arg-type]
    assert "No relevant passages" in tool.invoke({"query": "q"})


def test_conversation_tool_binds_conversation_filter_and_name() -> None:
    """Bug 2 / §8.5.3: the per-turn tool is named ``search_uploaded_files`` and binds a
    conversation-only filter (no team/agent scope)."""
    org, conv = uuid4(), uuid4()
    store = _FakeStore([])
    tool = make_conversation_tool(store, org_id=org, conversation_id=conv, k=5)  # type: ignore[arg-type]
    assert tool.name == "search_uploaded_files"
    assert store.search_kwargs is not None
    assert store.search_kwargs["k"] == 5
    assert store.search_kwargs["filter"] == build_conversation_filter(
        org_id=org, conversation_id=conv
    )


def test_rag_builder_registers_on_registry_and_assembles() -> None:
    """The registry's previously-unbound `rag` capability is wired here (§10.5.4)."""
    store = _FakeStore([Document(page_content="x", metadata={"source_id": "s"})])
    registry = ToolRegistry()
    registry.register("rag", make_rag_tool_builder(store))  # type: ignore[arg-type]
    cfg = _cfg(capabilities=Capabilities(rag=True))
    tools = registry.assemble(cfg)
    assert len(tools) == 1
    assert tools[0].name == "search_knowledge"
