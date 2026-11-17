"""Migrations upgrade and downgrade cleanly on the test database."""

import pytest
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.models import Base
from tests.conftest import alembic_run

pytestmark = pytest.mark.db


async def public_tables(url: URL) -> set[str]:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
            return {r[0] for r in rows}
    finally:
        await engine.dispose()


async def scalar(url: URL, sql: str) -> object:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return await conn.scalar(text(sql))
    finally:
        await engine.dispose()


async def test_downgrade_to_base_and_upgrade_to_head(migrated_database: URL) -> None:
    expected = set(Base.metadata.tables)

    alembic_run("downgrade", "base")
    assert await public_tables(migrated_database) <= {"alembic_version"}
    assert (
        await scalar(migrated_database, "SELECT 1 FROM pg_extension WHERE extname='vector'") is None
    )

    alembic_run("upgrade", "head")
    assert await public_tables(migrated_database) == expected | {"alembic_version"}
    assert await scalar(migrated_database, "SELECT 1 FROM pg_extension WHERE extname='vector'") == 1


async def test_embedding_column_matches_setting(migrated_database: URL) -> None:
    """Fails when EMBEDDING_DIMENSIONS changed without a migration for the new dimension."""
    column_type = await scalar(
        migrated_database,
        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
        "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'",
    )
    assert column_type == f"vector({settings.embedding_dimensions})"


async def test_hnsw_cosine_index_exists(migrated_database: URL) -> None:
    indexdef = await scalar(
        migrated_database,
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_chunks_embedding_hnsw'",
    )
    assert isinstance(indexdef, str)
    assert "hnsw" in indexdef and "vector_cosine_ops" in indexdef
