"""Teams & agents tables (TECHNICAL §11.2).

A ``team`` owns ``agents`` (peer ReAct configs) and references ``skills`` through
``agent_skills``. ``agents`` selects a model via ``profile_id`` (+ optional
``override_model_id``, ARCH Q1). Capability/knowledge toggles live in ``capabilities``
JSONB and map to predefined tools at spawn (ARCH §10.5.4).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import OrgScopedMixin, SoftDeleteMixin, TimestampMixin, UUIDPKMixin


class Team(UUIDPKMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A workspace of peer agents collaborating toward one goal (ARCH §1)."""

    __tablename__ = "teams"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal_title: Mapped[str | None] = mapped_column(String, nullable=True)
    goal_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_criteria: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    # Runtime-selected embedding model for this team's knowledge/memory (ARCH §9.5).
    # FK -> a model_catalog row with model_type='embedding'; NULL falls back to the
    # org default at resolution time (app.knowledge embedding resolver). The pgvector
    # collection is keyed by the resolved model, so the dimension stays sticky (§20 n6).
    embedding_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_catalog.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "uq_team_name_per_org",
            "org_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class Agent(UUIDPKMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One peer ReAct agent's stored configuration (ARCH §22.1)."""

    __tablename__ = "agents"

    team_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)  # system prompt
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    memory_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inference_profiles.id"), nullable=True
    )
    override_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_catalog.id"), nullable=True
    )
    # Optional per-agent embedding override for this agent's PRIVATE knowledge/memory.
    # NULL → use the team's embedding model (then org default). FK -> embedding-type
    # model_catalog row. Resolution chain: agent → team → org default (ARCH §9.5).
    embedding_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("model_catalog.id"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Skill(UUIDPKMixin, OrgScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A SKILL.md skill — filesystem base or UI-uploaded (ARCH §11/§26)."""

    __tablename__ = "skills"

    team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True
    )  # NULL = org/global base skill
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)  # the 'when-to-use'
    source: Mapped[str] = mapped_column(String, nullable=False)  # 'filesystem'|'uploaded'
    body_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    assets: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("source IN ('filesystem','uploaded')", name="ck_skill_source"),
        # Uniqueness within (org, team-or-global, name); COALESCE folds NULL team_id
        # to a sentinel so global skills collide as a single namespace (§11.2).
        Index(
            "uq_skill_name",
            "org_id",
            text("COALESCE(team_id, '00000000-0000-0000-0000-000000000000')"),
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class AgentSkill(Base):
    """Derived agent↔skill link; hard ``ON DELETE CASCADE`` (§11.2)."""

    __tablename__ = "agent_skills"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
