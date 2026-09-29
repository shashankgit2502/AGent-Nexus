"""Async knowledge ingestion worker (ARCH §10.5.1 / §21.3, ITEM 2 root-cause #1).

The piece that was missing: something that actually *runs* ingestion and moves a
source out of ``pending``. On register/upload the API spawns :func:`spawn_ingestion`;
on startup :func:`recover_stuck_sources` re-enqueues anything left ``pending`` or
``ingesting`` by a crash/restart (durability without a broker — the ``status``
column *is* the job state).

Concurrency model
-----------------
DB reads/writes are async (asyncpg/SQLAlchemy); the embedding + PGVector write path
is **sync** (psycopg). So each job runs in two phases:

1. **async** — load the source row, flip it to ``ingesting``, resolve which embedding
   model to use (agent → team → org default) and snapshot the model-layer rows the
   sync phase needs.
2. **sync, in a thread** (:func:`asyncio.to_thread`, time-boxed) — build the embedding
   client + the per-model PGVector collection, load the document(s), split, embed,
   write; return ``chunk_count``.

On success → ``ready`` + ``chunk_count``; on any failure → ``failed`` + ``error``
(R3: the cause is recorded and surfaced, never swallowed, never left hanging).

The worker owns its **own** DB session (not the request's, which closes when the
HTTP response returns) and sets the RLS GUC itself, exactly like ``core.deps.get_db``.
The ``IngestService.run`` seam keeps this swappable for a Redis/arq out-of-process
worker later (§21.3) with no API changes.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from langchain_core.documents import Document
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.secrets import build_secret_resolver
from app.db.models import KnowledgeSource
from app.db.models import LLMConnection as ConnRow
from app.db.models import ModelCatalog as CatalogRow
from app.db.session import AsyncSessionLocal
from app.knowledge.db_loader import load_db_documents
from app.knowledge.embedding_selection import (
    org_default_vision_model_id,
    resolve_embedding_model_id,
)
from app.knowledge.image_processing import build_load_context, ocr_available
from app.knowledge.ingest import IngestionService
from app.knowledge.loaders import LoadContext, UnsupportedFileFormat, load_source_documents
from app.knowledge.store import (
    build_knowledge_vectorstore,
    knowledge_collection_name,
    knowledge_connection_url,
)
from app.knowledge.unstructured_fallback import partition_with_unstructured
from app.models_layer.catalog import CatalogModel, InMemoryCatalogRepository
from app.models_layer.connections import InMemoryConnectionRepository
from app.models_layer.connections import LLMConnection as ConnDomain
from app.models_layer.embeddings import EmbeddingsResolver
from app.models_layer.profiles import InMemoryProfileRepository
from app.models_layer.resolver import ModelResolver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _IngestPrep:
    """Everything the sync embed phase needs, snapshotted from the async phase."""

    source_id: UUID
    org_id: UUID
    team_id: UUID | None
    agent_id: UUID | None
    conversation_id: UUID | None
    kind: str
    uri: str | None
    text: str | None
    embedding_model_id: UUID
    vision_model_id: UUID | None
    connector_config: dict[str, Any] | None
    connections: list[ConnDomain]
    catalog: list[CatalogModel]
    connection_url: str


async def _set_status(
    db: AsyncSession,
    source: KnowledgeSource,
    status: str,
    *,
    chunk_count: int | None = None,
    error: str | None = None,
) -> None:
    """Update a source's lifecycle status (and chunk_count/error), then commit."""
    source.status = status
    source.error = error
    if chunk_count is not None:
        source.chunk_count = chunk_count
    source.updated_at = datetime.now(UTC)
    await db.flush()
    await db.commit()


async def _prepare(db: AsyncSession, source: KnowledgeSource, *, settings: Settings) -> _IngestPrep:
    """Resolve the embedding model + snapshot model-layer rows for the sync phase."""
    embedding_model_id = await resolve_embedding_model_id(
        db, org_id=source.org_id, team_id=source.team_id, agent_id=source.agent_id
    )
    vision_model_id = await org_default_vision_model_id(db, source.org_id)
    conns = (
        await db.scalars(
            select(ConnRow).where(ConnRow.org_id == source.org_id, ConnRow.deleted_at.is_(None))
        )
    ).all()
    cats = (
        await db.scalars(
            select(CatalogRow).where(
                CatalogRow.org_id == source.org_id, CatalogRow.deleted_at.is_(None)
            )
        )
    ).all()
    return _IngestPrep(
        source_id=source.id,
        org_id=source.org_id,
        team_id=source.team_id,
        agent_id=source.agent_id,
        conversation_id=source.conversation_id,
        kind=source.kind,
        uri=source.uri,
        text=None,  # team_doc inline text not stored in v1; file kind reads from uri
        embedding_model_id=embedding_model_id,
        vision_model_id=vision_model_id,
        connector_config=source.connector_config,
        connections=[
            ConnDomain(
                id=c.id,
                display_name=c.display_name,
                provider=c.provider,
                base_url=c.base_url,
                api_key_ref=c.api_key_ref,
                api_version=c.api_version,
                enabled=c.enabled,
                validated_at=c.validated_at,
            )
            for c in conns
        ],
        catalog=[
            CatalogModel(
                id=m.id,
                provider_connection_id=m.provider_connection_id,
                display_name=m.display_name,
                model_identifier=m.model_identifier,
                model_type=m.model_type,
                deployment_name=m.deployment_name,
                supports_tools=m.supports_tools,
                supports_streaming=m.supports_streaming,
                supports_vision=m.supports_vision,
                supports_reasoning=m.supports_reasoning,
                context_window=m.context_window,
                enabled=m.enabled,
            )
            for m in cats
        ],
        connection_url=knowledge_connection_url(settings.LANGGRAPH_PG_URL),
    )


def _load_documents(prep: _IngestPrep, ctx: LoadContext, settings: Settings) -> list[Document]:
    """Load a source's documents per kind, incl. Slice-D db connector + long-tail fallback.

    * ``db`` — run the read-only SELECT from ``connector_config`` (handled here, not in
      the pure loader registry, because it is live I/O against a user DSN).
    * everything else — the universal loader registry; for a ``file`` whose format has
      no native loader, fall back to subprocess-isolated ``unstructured`` (Slice D).
    """
    if prep.kind == "db":
        cfg = prep.connector_config or {}
        dsn, query = cfg.get("dsn"), cfg.get("query")
        if not dsn or not query:
            raise ValueError("kind='db' requires connector_config with 'dsn' and 'query'")
        return load_db_documents(dsn, query)

    # allow_private only in local dev — lets a url source reach a loopback/private
    # host (e.g. a dev server); in prod the SSRF guard rejects them (§9.4).
    try:
        return load_source_documents(
            prep.kind, uri=prep.uri, text=prep.text, ctx=ctx, allow_private=settings.is_local
        )
    except UnsupportedFileFormat:
        # Long-tail fallback (Slice D): a file format with no native loader → try
        # unstructured in an isolated subprocess. Re-raise the original (clear) error
        # if it can't extract text, so the source fails with a precise reason.
        documents: list[Document] = []
        if prep.kind == "file" and prep.uri:
            documents = partition_with_unstructured(prep.uri, prep.uri)
        if not documents:
            raise
        return documents


def _embed_and_store(prep: _IngestPrep, settings: Settings) -> int:
    """Sync phase: build embeddings + per-model collection, load (w/ vision/OCR), embed.

    Runs in a worker thread (:func:`asyncio.to_thread`) because the embedding client,
    vision model, and PGVector are synchronous. Reuses the real
    :class:`EmbeddingsResolver` / :class:`ModelResolver` / :class:`IngestionService`
    (R2 — no hand-rolled embed/store/vision path). Returns the chunk count.
    """
    conn_repo = InMemoryConnectionRepository(prep.connections)
    cat_repo = InMemoryCatalogRepository(prep.catalog)
    secrets = build_secret_resolver(settings)

    embeddings = EmbeddingsResolver(
        connections=conn_repo, catalog=cat_repo, secrets=secrets
    ).resolve(prep.embedding_model_id)
    vector_store = build_knowledge_vectorstore(
        embeddings=embeddings,
        connection=prep.connection_url,
        collection_name=knowledge_collection_name(prep.embedding_model_id),
    )

    # Image enrichment context (Slice C): vision caption (org-default vision model,
    # if any) + OCR (only when the tesseract binary is present). With neither, image
    # content yields no text and an image-only source fails with a clear reason.
    vision_model = None
    if prep.vision_model_id is not None:
        model_resolver = ModelResolver(
            connections=conn_repo,
            catalog=cat_repo,
            profiles=InMemoryProfileRepository([]),
            secrets=secrets,
        )
        vision_model = model_resolver.resolve_catalog_model(
            prep.vision_model_id, require_tools=False
        )
    ctx = build_load_context(vision_model=vision_model, ocr_enabled=ocr_available())

    documents = _load_documents(prep, ctx, settings)
    return IngestionService(vector_store).ingest(
        documents,
        org_id=prep.org_id,
        team_id=prep.team_id,
        source_id=prep.source_id,
        agent_id=prep.agent_id,
        conversation_id=prep.conversation_id,
    )


async def run_ingestion(*, source_id: UUID, org_id: UUID, settings: Settings | None = None) -> None:
    """Ingest one knowledge source end-to-end, owning its own DB session (RLS-scoped).

    Idempotent-safe: a source already ``ready`` is skipped; a missing/deleted source
    is a no-op. Any failure is recorded on the row as ``failed`` + ``error`` and
    logged with the full traceback — never raised out of the background task (which
    would be lost), never swallowed silently (R3).
    """
    settings = settings or get_settings()
    async with AsyncSessionLocal() as db:
        # Session-level GUC so RLS applies across the multiple commits below.
        await db.execute(
            text("SELECT set_config('app.current_org', :org, false)"), {"org": str(org_id)}
        )
        source = await db.scalar(
            select(KnowledgeSource).where(
                KnowledgeSource.id == source_id,
                KnowledgeSource.org_id == org_id,
                KnowledgeSource.deleted_at.is_(None),
            )
        )
        if source is None:
            logger.warning("ingestion: source %s not found (deleted?) — skipping", source_id)
            return
        if source.status == "ready":
            return

        await _set_status(db, source, "ingesting")
        try:
            prep = await _prepare(db, source, settings=settings)
            chunk_count = await asyncio.wait_for(
                asyncio.to_thread(_embed_and_store, prep, settings),
                timeout=settings.KNOWLEDGE_INGEST_TIMEOUT_S,
            )
            await _set_status(db, source, "ready", chunk_count=chunk_count, error=None)
            logger.info("ingestion: source %s ready (%d chunks)", source_id, chunk_count)
        except Exception as exc:  # noqa: BLE001 — recorded on the row + logged, not swallowed
            await db.rollback()
            await db.execute(
                text("SELECT set_config('app.current_org', :org, false)"), {"org": str(org_id)}
            )
            fresh = await db.get(KnowledgeSource, source_id)
            if fresh is not None:
                await _set_status(db, fresh, "failed", error=str(exc))
            logger.exception("ingestion: source %s failed", source_id)


def spawn_ingestion(app: FastAPI, *, source_id: UUID, org_id: UUID) -> asyncio.Task[None]:
    """Schedule background ingestion of one source, tracked + awaited on shutdown.

    Mirrors the run-task pattern (ARCH §24.5): the task is strongly referenced in
    ``app.state.ingest_tasks`` so asyncio cannot GC it mid-flight, and the lifespan
    awaits in-flight tasks on shutdown so ingestion finishes cleanly.
    """
    tasks: set[asyncio.Task[None]] = app.state.ingest_tasks
    task = asyncio.create_task(run_ingestion(source_id=source_id, org_id=org_id))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task


async def recover_stuck_sources(app: FastAPI) -> int:
    """Re-enqueue sources left ``pending``/``ingesting`` by a crash/restart (durability).

    Runs once at startup before serving requests. Queries across orgs (no RLS GUC —
    startup, like the org seed) and spawns a background ingestion per stuck source.
    Returns how many were re-enqueued (for logging/tests).
    """
    async with AsyncSessionLocal() as db:
        rows = (
            await db.scalars(
                select(KnowledgeSource).where(
                    KnowledgeSource.status.in_(("pending", "ingesting")),
                    KnowledgeSource.deleted_at.is_(None),
                )
            )
        ).all()
    for src in rows:
        spawn_ingestion(app, source_id=src.id, org_id=src.org_id)
    if rows:
        logger.info("ingestion: re-enqueued %d stuck source(s) on startup", len(rows))
    return len(rows)
