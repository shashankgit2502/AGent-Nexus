"""Model Resolution Layer tables (TECHNICAL §11.3, ARCH §9/§27).

``llm_connections`` (Layer 1) → ``model_catalog`` (Layer 2) → ``inference_profiles``
(Layer 3). The DB stores only an ``api_key_ref`` (a reference into the secrets
manager — never the key, ARCH §9.4). ``supports_tools`` on a catalog row is the
hard gate for mesh agents (ARCH §9.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import OrgScopedMixin, SoftDeleteMixin, TimestampMixin, UUIDPKMixin


class LLMConnection(UUIDPKMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One configured way to reach a provider (Layer 1, §11.3)."""

    __tablename__ = "llm_connections"

    display_name: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    api_key_ref: Mapped[str | None] = mapped_column(String, nullable=True)  # secrets-manager ref
    api_version: Mapped[str | None] = mapped_column(String, nullable=True)
    scope: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'org'"))
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    validated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "provider IN ('openai','anthropic','azure_openai','ollama','openrouter',"
            "'openai_compatible')",
            name="ck_conn_provider",
        ),
        CheckConstraint("scope IN ('org','team')", name="ck_conn_scope"),
    )


class ModelCatalog(UUIDPKMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One model reachable through a connection (Layer 2, §11.3)."""

    __tablename__ = "model_catalog"

    provider_connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("llm_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    model_identifier: Mapped[str] = mapped_column(
        String, nullable=False
    )  # passed through unchanged
    model_type: Mapped[str] = mapped_column(String, nullable=False)  # 'chat'|'embedding'
    deployment_name: Mapped[str | None] = mapped_column(String, nullable=True)  # azure, per-model
    supports_tools: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )  # HARD GATE (ARCH §9.3)
    supports_streaming: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    supports_vision: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    supports_reasoning: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pricing: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(
        String, nullable=False
    )  # 'discovered'|'models.dev'|'manual'
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint("model_type IN ('chat','embedding')", name="ck_catalog_model_type"),
        CheckConstraint("source IN ('discovered','models.dev','manual')", name="ck_catalog_source"),
        Index(
            "uq_catalog_model",
            "provider_connection_id",
            "model_identifier",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Partial index serving the "tool-capable models" dropdown (ARCH §9.3).
        Index(
            "ix_catalog_tools",
            "org_id",
            postgresql_where=text("supports_tools AND deleted_at IS NULL"),
        ),
    )


class InferenceProfile(UUIDPKMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A reusable default-model + normalized params bundle (Layer 3, §11.3)."""

    __tablename__ = "inference_profiles"

    name: Mapped[str] = mapped_column(String, nullable=False)
    default_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_catalog.id"), nullable=True
    )
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_level: Mapped[str | None] = mapped_column(String, nullable=True)
    json_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
