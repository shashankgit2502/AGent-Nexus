"""Reusable column mixins enforcing the TECHNICAL §11.0 conventions.

Every tenant table follows the same skeleton (§11.0):

* **PK** ``id UUID`` defaulting to ``gen_random_uuid()``.
* **Timestamps** ``created_at`` / ``updated_at`` (``TIMESTAMPTZ``); ``updated_at``
  is also maintained by a DB trigger (§11.6) — the ``onupdate`` here keeps the
  ORM-side value coherent within a session, the trigger is the DB-side guarantee.
* **Soft-delete** ``deleted_at`` on core entities; reads filter
  ``deleted_at IS NULL`` and uniqueness uses partial indexes (authored in the
  migration, not here).
* **Tenancy** ``org_id`` FK on every tenant-scoped table → the RLS key (§11.5/§11.7).

SQLAlchemy 2.0 copies a ``mapped_column`` defined on a mixin into each mapped
subclass (including its ``ForeignKey``), so these mixins compose cleanly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPKMixin:
    """Primary key ``id UUID`` defaulting to ``gen_random_uuid()`` (§11.0)."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """``created_at`` / ``updated_at`` (``TIMESTAMPTZ NOT NULL``, §11.0/§11.6)."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),  # ORM-side; the DB trigger (§11.6) is the source of truth
    )


class SoftDeleteMixin:
    """``deleted_at`` for core entities (§11.0). ``NULL`` ⇒ live row."""

    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class OrgScopedMixin:
    """``org_id`` FK to the top tenant — the RLS key (§11.0/§11.5).

    Hard ``ON DELETE CASCADE``: deleting an organization removes all its data.
    """

    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
