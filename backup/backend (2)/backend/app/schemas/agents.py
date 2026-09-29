"""Agent request/response DTOs (ARCH §14/§22, TECHNICAL §11.2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AgentCreate(BaseModel):
    """Payload for ``POST /teams/{id}/agents`` (ARCH §14).

    ``capabilities`` is the toggle map (rag/web_search/code_interpreter/doc_chart/
    image_gen → predefined tools, ARCH §10.5.4). ``profile_id`` selects the model
    bundle; ``override_model_id`` is the optional ARCH-Q1 model override.
    """

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    instructions: str | None = None
    capabilities: dict[str, bool] = Field(default_factory=dict)
    memory_enabled: bool = False
    profile_id: UUID | None = None
    override_model_id: UUID | None = None
    # Optional per-agent embedding override for this agent's private knowledge/memory
    # (ARCH §9.5). NULL → team's embedding model → org default.
    embedding_model_id: UUID | None = None


class AgentUpdate(BaseModel):
    """Partial update for ``PUT /agents/{id}`` — only provided fields change."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    instructions: str | None = None
    capabilities: dict[str, bool] | None = None
    memory_enabled: bool | None = None
    profile_id: UUID | None = None
    override_model_id: UUID | None = None
    embedding_model_id: UUID | None = None


class AgentRead(ORMModel):
    """Agent config as returned to clients."""

    id: UUID
    org_id: UUID
    team_id: UUID
    name: str
    description: str | None
    instructions: str | None
    capabilities: dict[str, bool]
    memory_enabled: bool
    profile_id: UUID | None
    override_model_id: UUID | None
    embedding_model_id: UUID | None
    created_at: datetime
