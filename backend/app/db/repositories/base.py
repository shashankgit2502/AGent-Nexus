"""Generic org-scoped async repository (repository pattern, CLAUDE patterns).

Every CRUD router shares this thin data-access layer so business rules — *always
filter by ``org_id``* (defence-in-depth alongside RLS, §11.7) and *exclude
soft-deleted rows* — live in one place rather than being re-implemented per router
(R5: logic out of routers). Columns are reached through an ``Any``-typed alias of
the model class (``_cols``) because the model is a generic ``type[ModelT]`` whose
declared columns aren't visible on the ``Base`` bound — this keeps the base reusable
and type-checks cleanly without per-call ignores.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement, Select

from app.db.base import Base


class OrgScopedRepository[ModelT: Base]:
    """Async CRUD for one org-scoped model, bound to a session + active org."""

    def __init__(self, session: AsyncSession, model: type[ModelT], org_id: UUID) -> None:
        self.session = session
        self.model = model
        self.org_id = org_id
        # Dynamic column access on the mapped class (org_id/id/deleted_at are declared
        # on mixins, not the Base bound). Typed Any so mypy stays clean.
        self._cols: Any = model

    def _select(self) -> Select[tuple[ModelT]]:
        """Base SELECT filtered by org + (if soft-deletable) live rows only."""
        stmt = select(self.model).where(self._cols.org_id == self.org_id)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self._cols.deleted_at.is_(None))
        return stmt

    async def get(self, id_: UUID) -> ModelT | None:
        """Return the row by id within this org, or ``None``."""
        stmt = self._select().where(self._cols.id == id_)
        result: ModelT | None = await self.session.scalar(stmt)
        return result

    async def list(
        self, *, order_by: str | None = None, descending: bool = False, **eq_filters: Any
    ) -> Sequence[ModelT]:
        """Return all matching rows in this org (optionally equality-filtered/ordered).

        ``order_by`` names a column on the model (e.g. ``"created_at"``); pair it
        with ``descending`` to flip direction. Ordering is opt-in so existing
        callers (equality filters only) are unaffected.
        """
        stmt = self._select()
        for name, value in eq_filters.items():
            stmt = stmt.where(getattr(self._cols, name) == value)
        if order_by is not None:
            column = getattr(self._cols, order_by)
            stmt = stmt.order_by(column.desc() if descending else column.asc())
        return (await self.session.scalars(stmt)).all()

    def _match_conditions(
        self,
        *,
        search: str | None,
        search_columns: Sequence[str],
        eq_filters: dict[str, Any],
    ) -> Sequence[ColumnElement[bool]]:
        """Build the equality + (optional) ILIKE-OR conditions shared by a page query
        and its count, so both filter identically (no drift between rows and total).

        Annotated with ``Sequence`` (not ``list[...]``) because a method named
        ``list`` on this class shadows the builtin inside class-scope annotations."""
        conds = [getattr(self._cols, name) == value for name, value in eq_filters.items()]
        if search and search_columns:
            like = f"%{search}%"
            conds.append(or_(*(getattr(self._cols, c).ilike(like) for c in search_columns)))
        return conds

    async def search_page(
        self,
        *,
        search: str | None = None,
        search_columns: Sequence[str] = (),
        limit: int = 50,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
        **eq_filters: Any,
    ) -> tuple[Sequence[ModelT], int]:
        """Return ``(page_items, total)`` for org-scoped rows, searched + paginated.

        ``search`` (with ``search_columns``) applies a case-insensitive OR-ed ILIKE
        across those columns; ``total`` is the full match count *before* limit/offset
        so the caller can paginate. Ordering defaults to ``created_at`` (when present)
        for a stable page window. Reused by Settings→AI model search and, later,
        Memory/Knowledge search (one place, defence-in-depth org filter intact).
        """
        conds = self._match_conditions(
            search=search, search_columns=tuple(search_columns), eq_filters=eq_filters
        )

        count_stmt = (
            select(func.count()).select_from(self.model).where(self._cols.org_id == self.org_id)
        )
        if hasattr(self.model, "deleted_at"):
            count_stmt = count_stmt.where(self._cols.deleted_at.is_(None))
        page_stmt = self._select()
        for cond in conds:
            count_stmt = count_stmt.where(cond)
            page_stmt = page_stmt.where(cond)

        total = int(await self.session.scalar(count_stmt) or 0)

        sort_col = order_by or ("created_at" if hasattr(self.model, "created_at") else None)
        if sort_col is not None:
            column = getattr(self._cols, sort_col)
            page_stmt = page_stmt.order_by(column.desc() if descending else column.asc())
        page_stmt = page_stmt.limit(limit).offset(offset)

        items = (await self.session.scalars(page_stmt)).all()
        return items, total

    async def add(self, obj: ModelT) -> ModelT:
        """Persist a new instance and refresh server-side defaults (id, timestamps)."""
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def soft_delete(self, id_: UUID) -> bool:
        """Soft-delete (or hard-delete derived rows) by id. Returns whether found."""
        obj = await self.get(id_)
        if obj is None:
            return False
        if hasattr(obj, "deleted_at"):
            obj_any: Any = obj
            obj_any.deleted_at = datetime.now(UTC)
        else:
            await self.session.delete(obj)
        await self.session.flush()
        return True
