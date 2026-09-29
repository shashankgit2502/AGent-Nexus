"""Knowledge vector store factory — pgvector via ``PGVector`` (ARCH §10.5 / §9.5).

The single place that constructs the knowledge ``PGVector`` store, so collection
name, JSONB metadata mode, and the connection string are configured once. Using
``langchain_postgres.PGVector`` (a real primitive, R2) keeps Knowledge, the
checkpointer, and the long-term Store all inside the one Postgres we already run
(§9.5).

Connection string: PGVector wants a SQLAlchemy/psycopg URL
(``postgresql+psycopg://…``). ``settings.LANGGRAPH_PG_URL`` is the bare
``postgresql://…`` psycopg URL used by the checkpointer/store; :func:`knowledge_connection_url`
normalises it to the ``+psycopg`` driver form PGVector expects.

Dimension is sticky (§9.5 / §20 note 6): the embedding model's output size fixes
the pgvector column width at collection creation. ``embedding_length`` is passed
through so the column is created at the right width; changing the embedding model
later is a re-index migration, not a silent swap.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from langchain_core.embeddings import Embeddings
from langchain_postgres import PGVector
from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

# The langchain-postgres chunk table (R1: verified for langchain-postgres 0.0.17;
# re-verify on upgrade — TECHNICAL §11.5 standing caveat). It lives in the same
# Postgres as the app tables, so a source's chunks can be deleted in the same
# request transaction as the source's soft-delete, by the globally-unique source_id
# carried in chunk metadata (no embeddings client / collection lookup required).
KNOWLEDGE_EMBEDDING_TABLE = "langchain_pg_embedding"

# Base name for knowledge collections. Tenant isolation *within* a collection is the
# metadata filter (§10.5.2); collections are split **per embedding model** (below).
KNOWLEDGE_COLLECTION = "knowledge"


def knowledge_collection_name(embedding_model_id: UUID) -> str:
    """The PGVector collection for one embedding model (ITEM 2, ARCH §9.5/§20 n6).

    The pgvector column dimension is fixed at collection creation and differs per
    embedding model, so two models **cannot** share a collection. We therefore key
    the collection by the resolved embedding ``model_catalog`` id: each model owns a
    ``knowledge__<model_id>`` collection at its own dimension. Retrieval resolves the
    agent's embedding model the same way and queries the matching collection, so
    vectors are only ever compared within one embedding space (the correct semantics —
    you cannot compare vectors across embedding models). Tenant scoping stays inside
    each collection via the metadata filter.
    """
    return f"{KNOWLEDGE_COLLECTION}__{embedding_model_id}"


def knowledge_connection_url(langgraph_pg_url: str) -> str:
    """Normalise a bare ``postgresql://`` URL to the ``postgresql+psycopg://`` PGVector wants."""
    if langgraph_pg_url.startswith("postgresql+"):
        return langgraph_pg_url
    if langgraph_pg_url.startswith("postgresql://"):
        return langgraph_pg_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return langgraph_pg_url


def build_knowledge_vectorstore(
    *,
    embeddings: Embeddings,
    connection: str,
    embedding_length: int | None = None,
    collection_name: str = KNOWLEDGE_COLLECTION,
) -> PGVector:
    """Construct the knowledge ``PGVector`` store (§10.5.1).

    Args:
        embeddings: the team's resolved embedding model (powers both ingest + search).
        connection: a ``postgresql+psycopg://…`` URL (see :func:`knowledge_connection_url`).
        embedding_length: the embedding dimension; fixes the pgvector column width
            (sticky, §9.5). ``None`` lets PGVector infer it on first write.
        collection_name: defaults to the single shared :data:`KNOWLEDGE_COLLECTION`.
    """
    return PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=connection,
        embedding_length=embedding_length,
        use_jsonb=True,  # JSONB metadata = the $and/$or/$in operators the filter uses
    )


async def delete_source_vectors(db: AsyncSession, *, source_id: UUID, org_id: UUID) -> int:
    """Hard-delete a source's chunk vectors by ``source_id`` metadata (ITEM 2).

    Run in the same request transaction as the source soft-delete so retrieval can
    never serve stale chunks. ``PGVector.delete`` is ids-only in 0.0.17, so we delete
    on the chunk table directly, filtering the JSONB ``cmetadata`` by the
    globally-unique ``source_id`` (plus ``org_id`` for defence-in-depth). If no
    source has been ingested yet the table may not exist — ``to_regclass`` guards
    that so a delete-before-any-ingest is a clean no-op, not an error. Returns the
    number of chunk rows removed.
    """
    exists = await db.scalar(text("SELECT to_regclass(:t)"), {"t": KNOWLEDGE_EMBEDDING_TABLE})
    if exists is None:
        return 0
    result = cast(
        "CursorResult[Any]",
        await db.execute(
            text(
                f"DELETE FROM {KNOWLEDGE_EMBEDDING_TABLE} "  # noqa: S608 — table is a vetted constant, not user input
                "WHERE cmetadata->>'source_id' = :sid AND cmetadata->>'org_id' = :org"
            ),
            {"sid": str(source_id), "org": str(org_id)},
        ),
    )
    return result.rowcount or 0
