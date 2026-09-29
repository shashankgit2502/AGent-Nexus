"""Knowledge ingestion core — split → stamp metadata → embed (ARCH §10.5.1).

The chunk+embed half of the pipeline. Loading (bytes/URI/text → ``Document``) lives
in :mod:`app.knowledge.loaders`; the async worker (:mod:`app.knowledge.worker`)
orchestrates load → this service → status update. Keeping ``ingest`` document-in /
count-out makes it storage- and format-agnostic and unit-testable with a fake store.

Each source's documents are split into overlapping chunks with the real
``RecursiveCharacterTextSplitter`` (R2), stamped with tenant/scope metadata
(§10.5.1), and written to the per-embedding-model ``PGVector`` collection — which
embeds them with the resolved embedding model on the way in.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.knowledge.metadata import chunk_metadata

# Defaults sized for prose RAG; tunable per team later. Overlap preserves context
# that would otherwise be cut mid-idea at a chunk boundary.
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200


class IngestionService:
    """Split documents, stamp tenant metadata, and add them to the vector store.

    Args:
        vector_store: the knowledge ``PGVector`` (or any ``VectorStore`` in tests).
        splitter: override the default recursive splitter (e.g. for code/markdown).
    """

    def __init__(
        self, vector_store: VectorStore, *, splitter: RecursiveCharacterTextSplitter | None = None
    ) -> None:
        self._vector_store = vector_store
        self._splitter = splitter or RecursiveCharacterTextSplitter(
            chunk_size=DEFAULT_CHUNK_SIZE, chunk_overlap=DEFAULT_CHUNK_OVERLAP
        )

    def ingest(
        self,
        documents: Sequence[Document],
        *,
        org_id: UUID,
        source_id: UUID,
        team_id: UUID | None = None,
        agent_id: UUID | None = None,
        conversation_id: UUID | None = None,
    ) -> int:
        """Chunk, tag, and embed one source's documents; return the chunk count.

        Scope (§10.5.1 / §8.5.3): ``conversation_id`` set → a **transient chat
        attachment**; ``agent_id`` set → **agent-private**; otherwise **team-shared**
        (see :func:`~app.knowledge.metadata.chunk_metadata`). Returns 0 (no write)
        when there is nothing to ingest, so an empty source is a no-op, not an error.
        """
        chunks = self._splitter.split_documents(list(documents))
        if not chunks:
            return 0

        metadata = chunk_metadata(
            org_id=org_id,
            team_id=team_id,
            source_id=source_id,
            agent_id=agent_id,
            conversation_id=conversation_id,
        )
        # New Document objects (don't mutate the splitter's output, coding-style §Immutability):
        # the source's loader metadata is preserved and the tenant metadata layered on top.
        tagged = [
            Document(page_content=chunk.page_content, metadata={**chunk.metadata, **metadata})
            for chunk in chunks
        ]
        self._vector_store.add_documents(tagged)
        return len(tagged)
