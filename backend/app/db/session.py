"""Async SQLAlchemy engine and session factory, built from DATABASE_URL."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.models  # noqa: F401  (register EVERY table, see below)
from app.core.config import settings

# Every model must be registered before the first flush: foreign keys such as
# usage_records.agent_run_id point at tables of modules the app may not have imported yet
# (workflow, rag, teaching). Without this, the first usage row fails in the running app.

# Seconds to wait for Postgres before giving up. Kept short so /health
# reports "down" quickly when the database is not running.
DB_CONNECT_TIMEOUT = 2.0

# Creating the engine does not connect yet; it connects on first use.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    # SQLAlchemy errors would otherwise print the bound values, which can be message text,
    # memory items or code (rule 53).
    hide_parameters=True,
    connect_args={"timeout": DB_CONNECT_TIMEOUT},  # asyncpg connect timeout
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""
    async with SessionLocal() as session:
        yield session
