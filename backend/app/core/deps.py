"""FastAPI dependency injection — org-scoped DB session, checkpointer, store.

The DB session dependency binds the request's :class:`OrgContext` to the database
transaction via ``set_config('app.current_org', <org>, true)`` so Row-Level
Security (TECHNICAL §11.7) applies to every query in the request. ``set_config``
with ``is_local=true`` is the parameterizable, transaction-scoped equivalent of
``SET LOCAL`` (which cannot take a bind parameter) — it is discarded on commit, so
the GUC never leaks across pooled connections.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import OrgContext, get_org_context
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def get_db(
    org: Annotated[OrgContext, Depends(get_org_context)],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an org-scoped async session (RLS GUC set), committing on success.

    The RLS scope is set at **session (connection) level** (``is_local=False``), not
    transaction-local: a single request may commit more than once (the run-launch
    route commits the ``runs`` row before streaming so the event store's own
    connections can reference it), and a transaction-local GUC would be lost after
    that commit — RLS would then block the later artifact insert. A session-level
    GUC survives commits; ``RESET`` on close stops it leaking to the next request on
    the pooled connection.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("SELECT set_config('app.current_org', :org, false)"),
            {"org": str(org.org_id)},
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # Clear the GUC before the connection returns to the pool (defence
            # against cross-request leakage; the pool's rollback-on-return does NOT
            # revert an already-committed session-level SET). Best-effort: a reset
            # failure must not mask the real error, but it is logged, not swallowed.
            try:
                await session.execute(text("RESET app.current_org"))
                await session.commit()
            except Exception:
                logger.warning("failed to reset RLS GUC on session close", exc_info=True)


# Convenience aliases for routers.
DbSession = Annotated[AsyncSession, Depends(get_db)]
Org = Annotated[OrgContext, Depends(get_org_context)]


def get_checkpointer(request: Request) -> Any:
    """Return the LangGraph PostgresSaver attached to app state at startup."""
    return request.app.state.checkpointer


def get_store(request: Request) -> Any:
    """Return the LangGraph PostgresStore attached to app state at startup."""
    return request.app.state.store
