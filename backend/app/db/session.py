"""Async SQLAlchemy engine and session factory, built from DATABASE_URL."""

import asyncio
import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.models  # noqa: F401  (register EVERY table, see below)
from app.core.config import settings

# Every model must be registered before the first flush: foreign keys such as
# usage_records.agent_run_id point at tables of modules the app may not have imported yet
# (workflow, rag, teaching). Without this, the first usage row fails in the running app.

logger = logging.getLogger(__name__)

# Seconds to wait for Postgres before giving up. Kept short so /health
# reports "down" quickly when the database is not running.
DB_CONNECT_TIMEOUT = 2.0

# Creating the engine does not connect yet; it connects on first use.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"timeout": DB_CONNECT_TIMEOUT},  # asyncpg connect timeout
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""
    async with SessionLocal() as session:
        yield session


async def check_database(timeout: float = DB_CONNECT_TIMEOUT) -> bool:
    """Return True if the database answers `SELECT 1`, False otherwise. Never raises.

    The whole check (connect + query) is capped at `timeout` seconds.
    """
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # health check must never crash
        logger.warning("Database health check failed: %s", exc)
        return False
