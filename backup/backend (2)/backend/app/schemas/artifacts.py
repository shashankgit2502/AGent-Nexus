"""Artifact API DTOs (ARTIFACTS.md §10/§12)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class IterateRequest(BaseModel):
    """Body for ``POST /artifacts/{id}/iterate`` — the Canvas edit/refine action (§10)."""

    instruction: str = Field(min_length=1, max_length=4000)


class ArtifactVersionRead(ORMModel):
    """One immutable version snapshot in the version switcher (§12)."""

    version: int
    size_bytes: int | None
    created_at: datetime


class ArtifactRead(ORMModel):
    """List/card view of an artifact (§12: kind icon, filename, size, version)."""

    id: UUID
    org_id: UUID
    run_id: UUID
    conversation_message_id: UUID | None
    producer_agent_id: UUID | None
    kind: str
    filename: str | None
    mime_type: str | None
    content_format: str
    size_bytes: int | None
    current_version: int
    status: str
    error: str | None
    created_at: datetime


class ArtifactDetail(ArtifactRead):
    """Metadata + version list + a freshly-signed download URL (§10 ``GET /artifacts/{id}``).

    ``download_url`` is minted per response so it always carries a non-expired token
    (§15); ``preview`` inlines small text content for the preview pane (§12), and is
    ``None`` for binary or storage-spilled artifacts.
    """

    download_url: str
    preview: str | None
    versions: list[ArtifactVersionRead]
