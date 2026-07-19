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
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models_layer.errors import EntityNotFound
from app.models_layer.translate_params import Provider


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
