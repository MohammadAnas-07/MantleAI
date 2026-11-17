"""Shared test fixtures.

Database tests run against a separate database, `mantle_test`, on the same server as
DATABASE_URL. It is created if missing and migrated to head once per test run. Each test runs
inside a transaction that is rolled back, so tests don't see each other's rows. The development
database `mantle` is never touched. When PostgreSQL is down, database tests are skipped.
"""

import asyncio
import threading
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import URL, make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import settings

TEST_DATABASE_NAME = "mantle_test"
BACKEND_DIR = Path(__file__).resolve().parents[1]


def get_test_database_url() -> URL:
    url = make_url(settings.database_url).set(database=TEST_DATABASE_NAME)
    assert url.database != "mantle", "tests must never use the development database"
    return url


def run_in_thread[T](func: Callable[[], T]) -> T:
    """Run `func` in a fresh thread, so code that calls asyncio.run() (Alembic's env.py) never
    meets an already running event loop."""
    result: dict[str, Any] = {}

    def target() -> None:
        try:
            result["value"] = func()
        except BaseException as exc:  # re-raised in the calling thread
            result["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result["value"]


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    url = get_test_database_url().render_as_string(hide_password=False)
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def alembic_run(action: str, revision: str) -> None:
    run_in_thread(lambda: getattr(command, action)(alembic_config(), revision))


async def _create_test_database() -> None:
    admin_url = get_test_database_url().set(database="postgres")
    engine = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool, connect_args={"timeout": 5}
    )
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DATABASE_NAME},
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE_NAME}"'))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def migrated_database() -> URL:
    """Create `mantle_test` if needed and migrate it to head. Skips if PostgreSQL is down."""
    try:
        run_in_thread(lambda: asyncio.run(_create_test_database()))
    except (OSError, TimeoutError) as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    alembic_run("upgrade", "head")
    return get_test_database_url()


@pytest.fixture(autouse=True)
def test_master_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """A fresh, generated master key for every test. Never a real key."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "master_encryption_key", key)
    return key


@pytest.fixture
async def engine(migrated_database: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back after the test."""
    async with engine.connect() as conn:
        transaction = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
