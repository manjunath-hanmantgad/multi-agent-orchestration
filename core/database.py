"""Async database engine and session management."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.schemas import Base

logger = logging.getLogger(__name__)
load_dotenv()


class DatabaseConfigurationError(RuntimeError):
    """Raised when required database configuration is missing."""


def get_database_url() -> str:
    """Return the configured database URL or raise a clear configuration error."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise DatabaseConfigurationError("Missing required environment variable: DATABASE_URL")
    return database_url


DATABASE_URL = get_database_url()
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session."""
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    """Create all ORM tables in the configured database."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except SQLAlchemyError as exc:
        logger.exception("database table creation failed: error_type=%s", type(exc).__name__)
        raise
