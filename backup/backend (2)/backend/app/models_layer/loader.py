"""Load the DB model layer into the in-memory domain repositories.

The Step 3/4 domain repositories (``ConnectionRepository`` / ``CatalogRepository``)
are **synchronous** Protocols consumed inside the graph, while the DB layer is
async. This module is the one place that bridges the two: it reads an org's live
``llm_connections`` + ``model_catalog`` rows and projects them into the frozen
domain models the resolver consumes.

It lives in ``models_layer`` rather than in the agent runtime because two very
different callers need it and neither should depend on the other:

* :mod:`app.agents.snapshot` — building a run's ``MeshContext``.
* :mod:`app.api.providers` — testing a connection through *exactly* the same
  construction the runtime performs. (A credential that passes its own test and
  then fails in a run because the two paths built it differently is the class of
  bug this shared loader exists to prevent.)

Keeping it here also keeps the API routers thin (R5): the providers router needs
a resolver, not the whole agent/knowledge/artifacts import graph.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LLMConnection as ConnRow
from app.db.models import ModelCatalog as CatalogRow
from app.models_layer.catalog import CatalogModel, InMemoryCatalogRepository
from app.models_layer.connections import InMemoryConnectionRepository, LLMConnection


async def load_conn_cat_repos(
    session: AsyncSession, *, org_id: UUID
) -> tuple[InMemoryConnectionRepository, InMemoryCatalogRepository]:
    """Load the org's connection + catalog rows into in-memory domain repos.

    Shared by the chat/mesh :class:`~app.models_layer.resolver.ModelResolver`, the
    knowledge :class:`~app.models_layer.embeddings.EmbeddingsResolver` and the
    Settings validation probe, so all three read the *same* Connection→Catalog
    snapshot (one query path, no drift between what a model resolves to, what an
    embedding resolves to, and what a connection test actually exercised).
    """
    conns = (
        await session.scalars(
            select(ConnRow).where(ConnRow.org_id == org_id, ConnRow.deleted_at.is_(None))
        )
    ).all()
    cats = (
        await session.scalars(
            select(CatalogRow).where(CatalogRow.org_id == org_id, CatalogRow.deleted_at.is_(None))
        )
    ).all()
    conn_repo = InMemoryConnectionRepository(
        [
            LLMConnection(
                id=c.id,
                display_name=c.display_name,
                provider=c.provider,
                base_url=c.base_url,
                api_key_ref=c.api_key_ref,
                api_version=c.api_version,
                enabled=c.enabled,
                validated_at=c.validated_at,
                # Gateway settings (Workbench headers). Without this the resolver
                # would build a workbench client with no charge code and no
                # subscription header — the fix would pass its unit tests and do
                # nothing at runtime.
                config_metadata=c.config_metadata or {},
            )
            for c in conns
        ]
    )
    cat_repo = InMemoryCatalogRepository(
        [
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
                # The declared request schema (auto/gpt4/gpt5). Carried so the
                # GPT-5 gate can honour a declaration at runtime — it is the only
                # way to classify an Azure deployment, whose name says nothing.
                model_family=m.model_family,
                enabled=m.enabled,
            )
            for m in cats
        ]
    )
    return conn_repo, cat_repo


__all__ = ["load_conn_cat_repos"]
