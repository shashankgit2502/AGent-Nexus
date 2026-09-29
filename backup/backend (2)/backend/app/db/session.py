"""Async SQLAlchemy engine and session factory."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

engine = create_async_engine(
    _settings.DATABASE_URL,
    # SQL logging is level-based via LOG_SQL (app.core.logging), never `echo`:
    # echo installs its own handler on sqlalchemy.engine alongside root
    # propagation, printing every statement twice.
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
