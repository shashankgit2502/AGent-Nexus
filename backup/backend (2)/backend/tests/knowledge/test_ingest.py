"""Ingestion pipeline tests (ARCH §10.5.1).

Split → stamp tenant/scope metadata → add. We drive the **real**
``RecursiveCharacterTextSplitter`` and a recording store double (the store
boundary), asserting the chunks carry the right tenant metadata and that
team-shared chunks never get an ``agent_id`` (the R1/R3 fix).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.knowledge.ingest import IngestionService
from app.knowledge.loaders import UnsupportedSourceKind, load_source_documents


class _RecordingStore:
    """Captures add_documents calls (stands in for PGVector at the store boundary)."""

    def __init__(self) -> None:
        self.added: list[Document] = []

    def add_documents(self, documents, **_kwargs):  # noqa: ANN001, ANN003, ANN201
        self.added.extend(documents)
        return [str(i) for i in range(len(documents))]


def _service() -> tuple[IngestionService, _RecordingStore]:
    store = _RecordingStore()
    splitter = RecursiveCharacterTextSplitter(chunk_size=40, chunk_overlap=5)
    return IngestionService(store, splitter=splitter), store


def test_ingest_splits_and_stamps_team_shared_metadata() -> None:
    svc, store = _service()
    org, team, src = uuid4(), uuid4(), uuid4()
    text = "Sentence number one is here. " * 12  # long enough to split into many chunks

    count = svc.ingest([Document(page_content=text)], org_id=org, team_id=team, source_id=src)

    assert count == len(store.added) > 1  # actually chunked
    for chunk in store.added:
        assert chunk.metadata["org_id"] == str(org)
        assert chunk.metadata["team_id"] == str(team)
        assert chunk.metadata["source_id"] == str(src)
        assert chunk.metadata["scope"] == "team"
        assert "agent_id" not in chunk.metadata  # no null stored (R1/R3 fix)


def test_ingest_agent_private_sets_scope_and_agent_id() -> None:
    svc, store = _service()
    agent = uuid4()
    svc.ingest(
        [Document(page_content="x" * 100)],
        org_id=uuid4(),
        team_id=uuid4(),
        source_id=uuid4(),
        agent_id=agent,
    )
    assert all(c.metadata["scope"] == "agent" for c in store.added)
    assert all(c.metadata["agent_id"] == str(agent) for c in store.added)


def test_ingest_conversation_attachment_sets_conversation_scope() -> None:
    """Bug 2 / §8.5.3: a chat upload is ingested as conversation-scoped (no team/agent)."""
    svc, store = _service()
    conv = uuid4()
    svc.ingest(
        [Document(page_content="z" * 100)], org_id=uuid4(), source_id=uuid4(), conversation_id=conv
    )
    assert store.added  # actually wrote chunks
    assert all(c.metadata["scope"] == "conversation" for c in store.added)
    assert all(c.metadata["conversation_id"] == str(conv) for c in store.added)
    assert all("agent_id" not in c.metadata for c in store.added)


def test_ingest_preserves_loader_metadata() -> None:
    svc, store = _service()
    svc.ingest(
        [Document(page_content="y" * 80, metadata={"path": "/docs/a.md"})],
        org_id=uuid4(),
        team_id=uuid4(),
        source_id=uuid4(),
    )
    assert all(c.metadata["path"] == "/docs/a.md" for c in store.added)


def test_ingest_empty_is_a_noop() -> None:
    svc, store = _service()
    assert svc.ingest([], org_id=uuid4(), team_id=uuid4(), source_id=uuid4()) == 0
    assert store.added == []


def test_load_team_doc_and_file(tmp_path) -> None:  # noqa: ANN001
    assert load_source_documents("team_doc", text="hello")[0].page_content == "hello"
    path = tmp_path / "doc.md"
    path.write_text("file body", encoding="utf-8")
    docs = load_source_documents("file", uri=str(path))
    assert docs[0].page_content == "file body"
    # The universal loader routes by format and tags the originating filename
    # (replaces the old single-path loader's "path" key).
    assert docs[0].metadata["filename"] == "doc.md"


def test_load_db_is_not_a_registry_loader() -> None:
    # url is handled in Slice D; db is loaded by the worker's connector, not here.
    with pytest.raises(UnsupportedSourceKind):
        load_source_documents("db", uri="postgres://x")


def test_load_requires_its_payload() -> None:
    with pytest.raises(ValueError, match="team_doc"):
        load_source_documents("team_doc")
    with pytest.raises(ValueError, match="file"):
        load_source_documents("file")
