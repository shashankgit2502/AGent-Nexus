"""Model Resolution Layer DTOs — connections / catalog / profiles (ARCH §14/§9/§27)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

Provider = Literal[
    "openai",
    "anthropic",
    "azure_openai",
    "ollama",
    "openrouter",
    "openai_compatible",
    "workbench",
]
ModelType = Literal["chat", "embedding"]

# Which request schema a catalog model follows (ARCH §9.2 / model_capabilities).
# ``auto`` = detect from the identifier + deployment name, which is what every
# model registered before this field existed resolves to.
ModelFamily = Literal["auto", "gpt4", "gpt5"]

# GPT-5 reasoning controls. ``minimal`` arrived with GPT-5; ``none``/``xhigh``/
# ``max`` with GPT-5.1+. The legacy ``low``/``medium``/``high`` are unchanged.
ReasoningLevel = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
Verbosity = Literal["low", "medium", "high"]


class WorkbenchFields(BaseModel):
    """The Workbench gateway settings carried on a connection.

    Stored in ``llm_connections.config_metadata`` (JSONB) rather than as discrete
    columns: gateway header sets are open-ended, and a new one must not require a
    migration. Every field is optional and ignored by every other provider.
    """

    workbench_provider: str | None = Field(
        default=None,
        max_length=50,
        description="Underlying model provider inside the gateway. Only 'openai' is implemented.",
    )
    charge_code: str | None = Field(
        default=None, max_length=50, description="Sent as the x-kpmg-charge-code header."
    )
    region_override: str | None = Field(
        default=None, max_length=100, description="Sent as the x-kpmg-region-override header."
    )
    azureml_model_deployment: str | None = Field(
        default=None, max_length=255, description="Sent as the azureml-model-deployment header."
    )


class ConnectionCreate(WorkbenchFields):
    """Payload for ``POST /providers/connections`` (ARCH §27.1).

    ``api_key_ref`` is a REFERENCE into the secrets manager — never the raw key
    (ARCH §9.4). The validation probe (ARCH §27.3) is invoked separately.
    """

    display_name: str = Field(min_length=1)
    provider: Provider
    base_url: str | None = None
    api_key_ref: str | None = None
    api_version: str | None = None
    scope: Literal["org", "team"] = "org"
    team_id: UUID | None = None


class ConnectionRead(ORMModel):
    id: UUID
    org_id: UUID
    display_name: str
    provider: str
    base_url: str | None
    api_version: str | None
    scope: str
    team_id: UUID | None
    enabled: bool
    validated_at: datetime | None
    created_at: datetime
    # Flattened from ``config_metadata`` by the router so the form can round-trip
    # without the client knowing the JSONB shape. Never carries a secret.
    workbench_provider: str | None = None
    charge_code: str | None = None
    region_override: str | None = None
    azureml_model_deployment: str | None = None


class ConnectionUpdate(WorkbenchFields):
    """Partial-edit payload for ``PUT /providers/connections/{id}`` (Bug 5 edit).

    Only fields explicitly set are applied (``model_dump(exclude_unset=True)``),
    so a caller can clear a nullable field by sending it as ``null``. Editing the
    key or endpoint invalidates the previous validation (handled in the router).
    """

    display_name: str | None = Field(default=None, min_length=1)
    provider: Provider | None = None
    base_url: str | None = None
    api_key_ref: str | None = None
    api_version: str | None = None
    enabled: bool | None = None


class ConnectionTestResult(BaseModel):
    """Result of ``POST /providers/connections/{id}/test`` (Bug 5 test button)."""

    ok: bool
    detail: str
    models_found: int
    validated_at: datetime | None


class CatalogModelCreate(BaseModel):
    """Payload for ``POST /providers/catalog`` — manual model registration (ARCH §27.2)."""

    provider_connection_id: UUID
    display_name: str = Field(min_length=1)
    model_identifier: str = Field(min_length=1)
    model_type: ModelType = "chat"
    deployment_name: str | None = None
    supports_tools: bool = False  # HARD GATE for mesh agents (ARCH §9.3)
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_reasoning: bool = False
    context_window: int | None = None
    # Which REQUEST SCHEMA this model follows. Distinct from supports_reasoning:
    # that says whether the model reasons, this says what the API accepts.
    # Required for Azure, whose deployment name carries no family signal.
    model_family: ModelFamily | None = None
    source: Literal["discovered", "models.dev", "manual"] = "manual"


class CatalogModelUpdate(BaseModel):
    """Partial edit for ``PATCH /providers/catalog/{id}`` (Approach B).

    Every field is optional — only those supplied are changed (``exclude_unset``).
    The load-bearing one is ``model_type``: it lets a mislabeled row (e.g. an
    embedding model discovery tagged ``chat``) be reclassified to ``embedding`` so it
    appears in the team embedding picker, without a delete + re-add.
    """

    display_name: str | None = Field(default=None, min_length=1)
    model_type: ModelType | None = None
    supports_tools: bool | None = None
    supports_streaming: bool | None = None
    supports_vision: bool | None = None
    supports_reasoning: bool | None = None
    context_window: int | None = None
    model_family: ModelFamily | None = None
    enabled: bool | None = None


class CatalogModelRead(ORMModel):
    id: UUID
    org_id: UUID
    provider_connection_id: UUID
    display_name: str
    model_identifier: str
    model_type: str
    deployment_name: str | None
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    supports_reasoning: bool
    context_window: int | None
    model_family: str | None
    source: str
    enabled: bool


class CatalogPage(BaseModel):
    """Paged listing of one connection's catalog models (ARCH §14, master-detail).

    Backs ``GET /providers/connections/{id}/models``: ``items`` is one page,
    ``total`` is the full match count (after ``q``/``supports_tools`` filtering,
    before paging) so the UI can render "showing N of total" and page controls.
    """

    items: list[CatalogModelRead]
    total: int
    limit: int
    offset: int


class ProfileCreate(BaseModel):
    """Payload for ``POST /providers/profiles`` (ARCH §27.4)."""

    name: str = Field(min_length=1)
    default_model_id: UUID | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    # Typed rather than free ``str``: an unrecognised effort is rejected by the
    # provider at request time, so it is cheaper to refuse it at the boundary
    # (R5). Widened for GPT-5 — the legacy low/medium/high remain valid.
    reasoning_level: ReasoningLevel | None = None
    # GPT-5 output-length control; sent only to reasoning models.
    verbosity: Verbosity | None = None
    json_mode: bool = False
    streaming: bool = True
    # Make this the org's default profile on create (ARCH §4.1/§4.6): its model runs
    # the planner + synthesizer. Setting it clears any previous default.
    is_default: bool = False


class ProfileUpdate(BaseModel):
    """Partial update for ``PATCH /providers/profiles/{id}`` — only present fields change.

    Exists primarily so a profile can be *selected* as the org default after creation;
    there was previously no update route at all (POST/GET/DELETE only), so a default
    could only ever be chosen at creation time.
    """

    name: str | None = Field(default=None, min_length=1)
    default_model_id: UUID | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    reasoning_level: ReasoningLevel | None = None
    verbosity: Verbosity | None = None
    json_mode: bool | None = None
    streaming: bool | None = None
    is_default: bool | None = None


class ProfileRead(ORMModel):
    id: UUID
    org_id: UUID
    name: str
    default_model_id: UUID | None
    temperature: float | None
    top_p: float | None
    max_tokens: int | None
    reasoning_level: str | None
    verbosity: str | None
    json_mode: bool
    streaming: bool
    is_default: bool
