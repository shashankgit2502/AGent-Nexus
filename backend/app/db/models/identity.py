"""Tenancy & identity tables (TECHNICAL §11.1).

Organization is the **top tenant** — every tenant-scoped table carries ``org_id``.
Auth is **external-IdP** (no passwords stored): a ``users`` row records the IdP
provider + subject. ``org_memberships`` is the user↔org join carrying the RBAC role.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPKMixin


class Organization(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """The top tenant. All tenant-scoped rows reference this via ``org_id``."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        # Uniqueness ignores soft-deleted rows (§11.0 partial unique index).
        Index("uq_org_slug", "slug", unique=True, postgresql_where=text("deleted_at IS NULL")),
    )


class User(UUIDPKMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An end user, identified by their external IdP subject (no passwords)."""

    __tablename__ = "users"

    idp_provider: Mapped[str] = mapped_column(String, nullable=False)  # 'clerk'|'auth0'|...
    idp_subject: Mapped[str] = mapped_column(String, nullable=False)  # IdP 'sub'
    email: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index(
            "uq_users_idp",
            "idp_provider",
            "idp_subject",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_users_email",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class OrgMembership(UUIDPKMixin, TimestampMixin, Base):
    """User↔org link carrying the RBAC role (owner/admin/member/viewer)."""

    __tablename__ = "org_memberships"

    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('owner','admin','member','viewer')", name="ck_membership_role"),
        UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),
    )
