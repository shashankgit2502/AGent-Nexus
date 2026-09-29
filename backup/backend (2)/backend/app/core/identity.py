"""Request identity / tenancy context (dev org-context, CLAUDE §3 RLS/tenancy).

The §11 schema makes ``org_id`` mandatory on every tenant table and RLS keys on
the ``app.current_org`` GUC (§11.5/§11.7). A real external-IdP auth layer (§11.1) is
a later concern; for the hackathon MVP this module provides a **dev org-context**:

* a single **default organization** is seeded at startup (idempotent);
* a request may override the active org/user via ``X-Org-Id`` / ``X-User-Id``
  headers (so multi-tenant behaviour and RLS are exercisable now);
* the DB session dependency (``app.core.deps.get_db``) issues
  ``set_config('app.current_org', <org>, true)`` per transaction so RLS applies.

This is deliberately the *only* deviation from §11.1's production identity model,
and it is additive — swapping in real IdP JWT validation later changes only
``get_org_context`` (it returns the same :class:`OrgContext`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Organization

logger = logging.getLogger(__name__)

DEFAULT_ORG_SLUG = "default"
DEFAULT_ORG_NAME = "Default Organization"


@dataclass(frozen=True)
class OrgContext:
    """The active tenant + user for one request (the RLS scope)."""

    org_id: UUID
    user_id: UUID | None = None


async def seed_default_organization(session: AsyncSession) -> UUID:
    """Ensure the dev default org exists; return its id (idempotent).

    ``organizations`` has no RLS (it is the tenant root), so this runs without an
    ``app.current_org`` GUC set — correct for startup seeding before any request.
    """
    existing = await session.scalar(
        select(Organization.id).where(
            Organization.slug == DEFAULT_ORG_SLUG, Organization.deleted_at.is_(None)
        )
    )
    if existing is not None:
        return existing
    org = Organization(name=DEFAULT_ORG_NAME, slug=DEFAULT_ORG_SLUG)
    session.add(org)
    await session.flush()  # populate org.id without ending the transaction
    logger.info("seeded default organization id=%s", org.id)
    return org.id


def get_org_context(
    request: Request,
    x_org_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> OrgContext:
    """Resolve the request's tenant context (dev mode).

    Precedence: ``X-Org-Id`` header → the seeded default org on ``app.state``.
    A malformed header is a client error (R5: validate at the boundary), not a
    silent fallback — that would cross tenants.
    """
    if x_org_id is not None:
        org_id = _parse_uuid(x_org_id, "X-Org-Id")
    else:
        default_org = getattr(request.app.state, "default_org_id", None)
        if default_org is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No org context: default organization not seeded.",
            )
        org_id = default_org
    user_id = _parse_uuid(x_user_id, "X-User-Id") if x_user_id is not None else None
    return OrgContext(org_id=org_id, user_id=user_id)


def _parse_uuid(value: str, field: str) -> UUID:
    """Parse a UUID header value, raising 400 on malformed input."""
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"{field} is not a valid UUID"
        ) from exc
