"""Async SQLAlchemy engine and session factory, built from DATABASE_URL."""

import asyncio
import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

# Creating the engine does not connect yet; it connects on first use.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"timeout": 3},  # asyncpg connect timeout in seconds
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""
    async with SessionLocal() as session:
        yield session


async def check_database(timeout: float = 3.0) -> bool:
    """Return True if the database answers `SELECT 1`, False otherwise. Never raises."""
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # health check must never crash
        logger.warning("Database health check failed: %s", exc)
        return False
