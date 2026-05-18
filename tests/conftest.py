"""Shared pytest fixtures for Enterprise Agentic Workflow Platform tests."""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.schemas import Base


@pytest_asyncio.fixture
async def in_memory_session_factory() -> async_sessionmaker[AsyncSession]:
    """Isolated in-memory SQLite session factory with full schema, per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield session_factory
    finally:
        await engine.dispose()
