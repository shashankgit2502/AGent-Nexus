"""Knowledge & RAG subsystem (ARCHITECTURE.md §10.5).

Ingest (load → split → embed → pgvector) and retrieve (tenant-filtered
``search_knowledge`` tool) over ``langchain_postgres.PGVector``. Public surface:

* :func:`~app.knowledge.store.build_knowledge_vectorstore` — the PGVector store.
* :class:`~app.knowledge.ingest.IngestionService` — chunk + tag + embed a source.
* :func:`~app.knowledge.retriever.make_rag_tool_builder` — register the ``rag``
  capability (§10.5.4) on the tool registry at the composition root.
* :func:`~app.knowledge.metadata.build_knowledge_filter` — the verified tenant filter.
"""

# Importing these modules registers their loaders on the universal registry:
# office formats (pdf/docx/xlsx/pptx, Slice B), images (png/jpg/…, Slice C), and the
# HTML→text loader for URL sources (Slice D). Imported for the side effect.
from app.knowledge import image_loaders as image_loaders  # noqa: E402,F401
from app.knowledge import office_loaders as office_loaders  # noqa: E402,F401
from app.knowledge import web_loader as web_loader  # noqa: E402,F401
from app.knowledge.ingest import IngestionService
from app.knowledge.loaders import (
    LoadContext,
    UnsupportedFileFormat,
    UnsupportedSourceKind,
    image_text_from,
    load_file_bytes,
    load_source_documents,
    register_file_loader,
    supported_file_formats,
)
from app.knowledge.metadata import build_knowledge_filter, chunk_metadata
from app.knowledge.retriever import make_knowledge_tool, make_rag_tool_builder
from app.knowledge.store import (
    build_knowledge_vectorstore,
    knowledge_collection_name,
    knowledge_connection_url,
)

__all__ = [
    "IngestionService",
    "LoadContext",
    "image_text_from",
    "load_source_documents",
    "load_file_bytes",
    "register_file_loader",
    "supported_file_formats",
    "UnsupportedFileFormat",
    "UnsupportedSourceKind",
    "build_knowledge_filter",
    "chunk_metadata",
    "make_knowledge_tool",
    "make_rag_tool_builder",
    "build_knowledge_vectorstore",
    "knowledge_collection_name",
    "knowledge_connection_url",
]
