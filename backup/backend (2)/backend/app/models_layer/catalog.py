"""Layer 2 — Model Catalog (ARCHITECTURE.md §9 / §27.2, TECHNICAL §11.3).

A *catalog model* is one model reachable through a connection. It carries the
``model_identifier`` passed through unchanged to the provider, the ``model_type``
(``chat`` vs ``embedding``, ARCH §9.5), the Azure ``deployment_name`` (per-model,
not per-connection), and the capability flags seeded from models.dev — of which
``supports_tools`` is the **hard gate** for mesh agents (ARCH §9.3).
"""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models_layer.errors import EntityNotFound
from app.models_layer.model_capabilities import ModelFamily

ModelType = Literal["chat", "embedding"]


class CatalogModel(BaseModel):
    """One model in the catalog (one row of ``model_catalog``)."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    provider_connection_id: UUID
    display_name: str
    model_identifier: str  # passed through unchanged (e.g. "anthropic/claude-…")
    model_type: ModelType = "chat"
    deployment_name: str | None = None  # azure_openai, per-model
    supports_tools: bool = False  # §9.3 hard gate for mesh agents
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_reasoning: bool = False
    context_window: int | None = None
    # Which REQUEST SCHEMA this model follows — distinct from ``supports_reasoning``,
    # which only describes whether the model reasons. ``None``/``auto`` means detect
    # from the identifier + deployment name; ``gpt5`` declares the GPT-5/o-series
    # schema (no temperature, no top_p). The declaration is the ONLY way to classify
    # an Azure deployment, whose name the customer chooses and which is what
    # ``discovery.py`` writes into ``model_identifier``.
    model_family: ModelFamily | None = None
    enabled: bool = True


class CatalogRepository(Protocol):
    """Read access to catalog models, by id (repository pattern)."""

    def get(self, model_id: UUID) -> CatalogModel: ...


class InMemoryCatalogRepository:
    """Dict-backed repository for tests and local dev (DB impl in Step 9)."""

    def __init__(self, models: list[CatalogModel] | None = None) -> None:
        self._by_id: dict[UUID, CatalogModel] = {m.id: m for m in (models or [])}

    def add(self, model: CatalogModel) -> None:
        self._by_id[model.id] = model

    def get(self, model_id: UUID) -> CatalogModel:
        try:
            return self._by_id[model_id]
        except KeyError as exc:
            raise EntityNotFound("catalog model", model_id) from exc
