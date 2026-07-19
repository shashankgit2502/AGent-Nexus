"""Step-7 knowledge acceptance — real pgvector tenant isolation (ARCH §10.5.2).

"Done when … ``search_knowledge`` returns only that team/agent's chunks." This
exercises the *whole* path against the live ``pgvector`` container — the real
``IngestionService`` → real ``PGVector`` → real ``make_knowledge_tool`` filter —
with deterministic fake embeddings (no provider/API key). It is the end-to-end
proof that the R1/R3 filter fix actually isolates tenants in the database, not
just in a unit assertion.

Skips automatically when Postgres is unreachable (e.g. CI without the container),
so the offline unit suite stays green; run ``docker compose up`` to execute it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from app.agents.config import AgentConfig, KnowledgeConfig
from app.core.config import get_settings
from app.knowledge.ingest import IngestionService
from app.knowledge.loaders import load_source_documents
from app.knowledge.retriever import make_conversation_tool, make_knowledge_tool
from app.knowledge.store import build_knowledge_vectorstore, knowledge_connection_url

_EMBED_DIM = 64


@pytest.fixture
def vector_store():  # noqa: ANN201
    """A real PGVector on a throwaway collection; skip if the DB is down."""
    psycopg_module = pytest.importorskip("psycopg")
    url = knowledge_connection_url(get_settings().LANGGRAPH_PG_URL)
    raw = url.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        psycopg_module.connect(raw, connect_timeout=3).close()
    except psycopg_module.OperationalError as exc:  # pragma: no cover - infra-dependent
        pytest.skip(f"Postgres not reachable for integration test: {exc}")

    store = build_knowledge_vectorstore(
        embeddings=DeterministicFakeEmbedding(size=_EMBED_DIM),
        connection=url,
        embedding_length=_EMBED_DIM,
        collection_name=f"knowledge_test_{uuid4().hex[:8]}",
    )
    yield store
    store.drop_tables()  # collection + this run's chunks only


def _agent_cfg(org_id, team_id, agent_id, **kw):  # noqa: ANN001, ANN003
    base = {
        "id": agent_id,
        "org_id": org_id,
        "team_id": team_id,
        "name": "agent",
        "profile_id": uuid4(),
    }
    base.update(kw)
    return AgentConfig(**base)


def test_search_knowledge_returns_only_that_team_and_agents_chunks(vector_store) -> None:  # noqa: ANN001
    svc = IngestionService(vector_store)
    org = uuid4()
    team_a, team_b = uuid4(), uuid4()
    agent_1, agent_2 = uuid4(), uuid4()
    src_shared_a, src_priv_1, src_priv_2, src_shared_b = (uuid4(), uuid4(), uuid4(), uuid4())

    svc.ingest(
        load_source_documents("team_doc", text="Team A shared playbook on pgvector."),
        org_id=org,
        team_id=team_a,
        source_id=src_shared_a,
    )
    svc.ingest(
        load_source_documents("team_doc", text="Agent one private note about pgvector."),
        org_id=org,
        team_id=team_a,
        source_id=src_priv_1,
        agent_id=agent_1,
    )
    svc.ingest(
        load_source_documents("team_doc", text="Agent two private note about pgvector."),
        org_id=org,
        team_id=team_a,
        source_id=src_priv_2,
        agent_id=agent_2,
    )
    svc.ingest(
        load_source_documents("team_doc", text="Team B shared secret about pgvector."),
        org_id=org,
        team_id=team_b,
        source_id=src_shared_b,
    )

    # Agent 1 of team A: sees team-A shared + its own private; NOT agent 2's, NOT team B.
    tool_1 = make_knowledge_tool(vector_store, cfg=_agent_cfg(org, team_a, agent_1), k=10)
    out_1 = tool_1.invoke({"query": "pgvector"})
    assert str(src_shared_a) in out_1
    assert str(src_priv_1) in out_1
    assert str(src_priv_2) not in out_1  # other agent's private chunk is invisible
    assert str(src_shared_b) not in out_1  # other team is invisible

    # "Only use specified sources" → restricts to the attached source only.
    tool_1_scoped = make_knowledge_tool(
        vector_store,
        cfg=_agent_cfg(
            org,
            team_a,
            agent_1,
            knowledge=KnowledgeConfig(only_specified_sources=True, source_ids=(src_shared_a,)),
        ),
        k=10,
    )
    out_scoped = tool_1_scoped.invoke({"query": "pgvector"})
    assert str(src_shared_a) in out_scoped
    assert str(src_priv_1) not in out_scoped  # own private excluded once scoped to a source


def test_conversation_attachments_isolated_from_other_conversations_and_team(vector_store) -> None:  # noqa: ANN001
    """Bug 2 / §8.5.3 acceptance: a chat upload is retrievable ONLY within its own
    conversation, and the transient namespace is invisible to team ``search_knowledge``.
    """
    svc = IngestionService(vector_store)
    org = uuid4()
    conv_a, conv_b = uuid4(), uuid4()
    team = uuid4()
    src_a, src_b, src_team = uuid4(), uuid4(), uuid4()

    svc.ingest(
        load_source_documents("team_doc", text="Conversation A upload about pgvector."),
        org_id=org,
        source_id=src_a,
        conversation_id=conv_a,
    )
    svc.ingest(
        load_source_documents("team_doc", text="Conversation B upload about pgvector."),
        org_id=org,
        source_id=src_b,
        conversation_id=conv_b,
    )
    svc.ingest(
        load_source_documents("team_doc", text="Team shared playbook about pgvector."),
        org_id=org,
        team_id=team,
        source_id=src_team,
    )

    # Conversation A's tool sees only A's upload — not B's, not the team KB.
    tool_a = make_conversation_tool(vector_store, org_id=org, conversation_id=conv_a, k=10)
    out_a = tool_a.invoke({"query": "pgvector"})
    assert str(src_a) in out_a
    assert str(src_b) not in out_a  # other conversation invisible
    assert str(src_team) not in out_a  # team KB invisible to the attachment tool

    # The team RAG tool must NOT see either conversation's transient attachments (§8.5.3).
    team_tool = make_knowledge_tool(vector_store, cfg=_agent_cfg(org, team, uuid4()), k=10)
    out_team = team_tool.invoke({"query": "pgvector"})
    assert str(src_team) in out_team
    assert str(src_a) not in out_team
    assert str(src_b) not in out_team
