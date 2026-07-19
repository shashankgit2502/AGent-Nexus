"""The ``search_knowledge`` retriever tool + its capability builder (ARCH §10.5.2).

This is what the **RAG capability** (§10.5.4) actually adds to an agent: a
metadata-filtered retriever wrapped as a LangChain tool, so the agent can only
ever retrieve knowledge it is entitled to (its org+team's shared sources OR its
own private sources — §10.5.2). The tenant filter is the security boundary, so it
is built from :func:`~app.knowledge.metadata.build_knowledge_filter` (verified
live against pgvector) and bound into the retriever per agent.

``make_rag_tool_builder`` produces a :data:`~app.tools.registry.ToolBuilder` so the
composition root can register RAG on the tool registry once the vector store
exists (the registry's `rag` capability was left unbound for exactly this step,
see its module docstring). Per-agent scoping (org/team/agent, the source toggles)
is read from the :class:`AgentConfig` at build time.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from langchain_core.documents import Document
from langchain_core.tools import BaseTool, tool
from langchain_core.vectorstores import VectorStore

from app.agents.config import AgentConfig
from app.knowledge.metadata import (
    CONVERSATION_TOOL_NAME,
    KNOWLEDGE_TOOL_NAME,
    build_conversation_filter,
    build_knowledge_filter,
)
from app.tools.registry import ToolBuilder

# Re-exported for callers that import them alongside the tool builders. The names
# themselves live in :mod:`app.knowledge.metadata` (a leaf) to keep the factory off
# the ``app.agents`` ↔ ``retriever`` import cycle. The decorated tool functions below
# MUST match these constants.
__all__ = [
    "CONVERSATION_TOOL_NAME",
    "KNOWLEDGE_TOOL_NAME",
    "make_conversation_tool",
    "make_knowledge_tool",
    "make_rag_tool_builder",
]

# Default top-k passages per search (matches ARCH §10.5.2's k=6).
DEFAULT_K = 6

logger = logging.getLogger(__name__)


def _format_passages(docs: Sequence[Document]) -> str:
    """Render retrieved chunks as source-attributed passages for the agent."""
    if not docs:
        return "No relevant passages found in the knowledge base."
    return "\n\n".join(f"[{doc.metadata.get('source_id', '?')}] {doc.page_content}" for doc in docs)


def _safe_retrieve(retriever: Any, query: str, *, what: str) -> str:
    """Retrieve passages, degrading gracefully if the lookup fails (R3/R5).

    A retrieval call embeds the query through the team's embedding model and hits
    pgvector — either can fail at runtime (a misconfigured / unreachable embedding
    endpoint, e.g. a 404 from the provider; a transient DB error). Such a failure
    must **not** abort the whole agent turn: in a ReAct loop a tool error is an
    *observation* the model can react to, not a fatal error. So we catch it, **log
    the full cause** for the operator (never silently swallowed — the root cause stays
    visible), and return an informative message so the agent continues without RAG
    instead of the entire multi-agent round collapsing to an abstention.
    """
    try:
        return _format_passages(retriever.invoke(query))
    except Exception as exc:  # noqa: BLE001 — a tool failure is a recoverable ReAct observation.
        logger.exception("%s failed for query %r", what, query)
        return (
            f"{what} is currently unavailable ({type(exc).__name__}: {exc}). "
            "This usually means the team's embedding model is misconfigured or "
            "unreachable. Proceed using your own knowledge and do not retry this tool."
        )


def make_knowledge_tool(
    vector_store: VectorStore,
    *,
    cfg: AgentConfig,
    k: int = DEFAULT_K,
) -> BaseTool:
    """Build the per-agent, tenant-filtered ``search_knowledge`` tool (§10.5.2)."""
    flt = build_knowledge_filter(
        org_id=cfg.org_id,
        team_id=cfg.team_id,
        agent_id=cfg.id,
        only_specified_sources=cfg.knowledge.only_specified_sources,
        source_ids=cfg.knowledge.source_ids,
    )
    retriever = vector_store.as_retriever(search_kwargs={"k": k, "filter": flt})

    @tool
    def search_knowledge(query: str) -> str:
        """Search the team/agent knowledge base for passages relevant to the query."""
        return _safe_retrieve(retriever, query, what="Knowledge search")

    return search_knowledge


def make_conversation_tool(
    vector_store: VectorStore,
    *,
    org_id: UUID,
    conversation_id: UUID,
    k: int = DEFAULT_K,
) -> BaseTool:
    """Build the per-turn ``search_uploaded_files`` tool for one conversation (§8.5.3).

    Unlike :func:`make_knowledge_tool` (a per-agent RAG capability), this is injected
    into the agent(s) for a turn whenever the conversation has uploaded files, so a
    user can ask about a freshly attached document regardless of any agent's RAG
    capability. It only ever sees **this conversation's** transient chunks
    (:func:`~app.knowledge.metadata.build_conversation_filter`).
    """
    flt = build_conversation_filter(org_id=org_id, conversation_id=conversation_id)
    retriever = vector_store.as_retriever(search_kwargs={"k": k, "filter": flt})

    @tool
    def search_uploaded_files(query: str) -> str:
        """Search files the user uploaded to THIS conversation for relevant passages."""
        return _safe_retrieve(retriever, query, what="Uploaded-file search")

    return search_uploaded_files


def make_rag_tool_builder(vector_store: VectorStore, *, k: int = DEFAULT_K) -> ToolBuilder:
    """Return the registry builder for the ``rag`` capability (§10.5.4).

    Register at the composition root::

        registry.register("rag", make_rag_tool_builder(knowledge_vectorstore))
    """

    def _builder(cfg: AgentConfig) -> list[BaseTool]:
        return [make_knowledge_tool(vector_store, cfg=cfg, k=k)]

    return _builder
