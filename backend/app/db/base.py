"""SQLAlchemy declarative base shared by all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All SQLAlchemy models inherit from this class.

    Alembic's autogenerate scans subclasses of Base to detect schema changes.
    Framework-managed tables (LangGraph checkpointer, PostgresStore, PGVector)
    are excluded via alembic/env.py's include_object filter (TECHNICAL §11.8).
    """
