"""Layer 1 — Provider Connections (ARCHITECTURE.md §9 / §27.1, TECHNICAL §11.3).

A *connection* is one configured way to reach a provider: its type, optional
``base_url``, an ``api_key_ref`` (a REFERENCE into the secrets manager — never
the key itself, ARCH §9.4), and validation state.

For Step 3 the connection is represented as a frozen Pydantic model plus a
``ConnectionRepository`` Protocol. An in-memory implementation backs unit tests
and local dev; the SQLAlchemy-backed implementation arrives with the schema in
Step 9 (TECHNICAL §11.3). The resolver depends only on the Protocol, so swapping
the backing store later is a one-line change (repository pattern).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models_layer.errors import EntityNotFound
from app.models_layer.translate_params import Provider

# Gateway metadata keys stored in ``llm_connections.config_metadata`` (JSONB).
# Kept as named constants so the writer (the API router) and the reader (the
# resolver) cannot drift — a typo on one side would silently drop a required
# header and produce a 401 from the gateway with no clue why.
WORKBENCH_PROVIDER_KEY = "workbench_provider"
WORKBENCH_CHARGE_CODE_KEY = "charge_code"
WORKBENCH_REGION_OVERRIDE_KEY = "region_override"
WORKBENCH_AZUREML_DEPLOYMENT_KEY = "azureml_model_deployment"

WORKBENCH_METADATA_KEYS: tuple[str, ...] = (
    WORKBENCH_PROVIDER_KEY,
    WORKBENCH_CHARGE_CODE_KEY,
    WORKBENCH_REGION_OVERRIDE_KEY,
    WORKBENCH_AZUREML_DEPLOYMENT_KEY,
)

DEFAULT_WORKBENCH_CHARGE_CODE = "0000"
"""Fallback ``x-kpmg-charge-code``. The gateway requires the header to exist;
the reference sends this placeholder when the registrar stated none."""


class WorkbenchConfig(BaseModel):
    """The Workbench gateway fields, read out of ``config_metadata``.

    A typed projection rather than raw dict access, so the resolver never digs
    into untrusted JSONB by hand (R5: validate at the boundary). Every field is
    optional — a connection that states none still builds, using the gateway's
    own defaults.
    """

    model_config = ConfigDict(frozen=True)

    workbench_provider: str = "openai"
    """The underlying model provider inside the gateway. Only ``openai`` is
    implemented; the others need their own Workbench API contract."""

    charge_code: str = DEFAULT_WORKBENCH_CHARGE_CODE
    region_override: str = ""
    azureml_model_deployment: str = ""


class LLMConnection(BaseModel):
    """A configured provider connection (one row of ``llm_connections``)."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    display_name: str
    provider: Provider
    base_url: str | None = None
    api_key_ref: str | None = None  # REFERENCE to a secret, never the secret
    api_version: str | None = None  # azure_openai default api version
    enabled: bool = True
    validated_at: datetime | None = None  # set by the validation probe (§27.3)
    # Open-ended, provider-specific connection settings (JSONB column). Today it
    # carries the Workbench gateway fields; it exists as JSONB rather than four
    # discrete columns because gateway header sets are genuinely open-ended and
    # a new one must not require a migration. NEVER holds a secret — the API key
    # stays behind ``api_key_ref`` (ARCH §9.4).
    config_metadata: dict[str, Any] = Field(default_factory=dict)

    def workbench(self) -> WorkbenchConfig:
        """The gateway settings for this connection, with defaults filled in.

        Tolerant by design: ``config_metadata`` is user-written JSONB, so a
        blank or absent key degrades to the default instead of failing a
        resolution that would otherwise succeed.
        """
        meta = self.config_metadata or {}
        return WorkbenchConfig(
            workbench_provider=str(meta.get(WORKBENCH_PROVIDER_KEY) or "openai").strip().lower(),
            charge_code=str(
                meta.get(WORKBENCH_CHARGE_CODE_KEY) or DEFAULT_WORKBENCH_CHARGE_CODE
            ).strip(),
            region_override=str(meta.get(WORKBENCH_REGION_OVERRIDE_KEY) or "").strip(),
            azureml_model_deployment=str(meta.get(WORKBENCH_AZUREML_DEPLOYMENT_KEY) or "").strip(),
        )


class ConnectionRepository(Protocol):
    """Read access to provider connections, by id (repository pattern)."""

    def get(self, connection_id: UUID) -> LLMConnection: ...


class InMemoryConnectionRepository:
    """Dict-backed repository for tests and local dev (DB impl in Step 9)."""

    def __init__(self, connections: list[LLMConnection] | None = None) -> None:
        self._by_id: dict[UUID, LLMConnection] = {c.id: c for c in (connections or [])}

    def add(self, connection: LLMConnection) -> None:
        self._by_id[connection.id] = connection

    def get(self, connection_id: UUID) -> LLMConnection:
        try:
            return self._by_id[connection_id]
        except KeyError as exc:
            raise EntityNotFound("connection", connection_id) from exc
