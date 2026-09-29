"""Team request/response DTOs (ARCH §14, TECHNICAL §11.2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class TeamCreate(BaseModel):
    """Payload for ``POST /teams`` (ARCH §14)."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    goal_title: str | None = None
    goal_description: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    # Runtime-selected embedding model for this team's knowledge/memory (ARCH §9.5).
    embedding_model_id: UUID | None = None


class TeamUpdate(BaseModel):
    """Partial update for ``PUT /teams/{id}`` — only present fields change (ARCH §14)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    goal_title: str | None = None
    goal_description: str | None = None
    success_criteria: list[str] | None = None
    embedding_model_id: UUID | None = None


class TeamRead(ORMModel):
    """Team as returned to clients."""

    id: UUID
    org_id: UUID
    name: str
    description: str | None
    goal_title: str | None
    goal_description: str | None
    success_criteria: list[str]
    embedding_model_id: UUID | None
    created_at: datetime
