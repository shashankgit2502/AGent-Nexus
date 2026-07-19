"""Async repositories (org-scoped data access) — see :mod:`base`."""

from __future__ import annotations

from app.db.repositories.base import OrgScopedRepository

__all__ = ["OrgScopedRepository"]
