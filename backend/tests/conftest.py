"""Shared test fixtures.

Database tests run against the database in TEST_DATABASE_URL, whose name must end in `_test`
(tests/db_guard.py). The guard runs in `pytest_configure`, before any test module is imported,
and stops the whole run if the setting is missing or names another database. Then the app's own
DATABASE_URL is replaced by it, so the app engine, alembic and anything that forgets a
dependency override can only reach the test database. It is migrated to head once per run; each
test runs inside a transaction that is rolled back. When PostgreSQL is down, database tests are
skipped. The tests never create or drop databases.
"""

import asyncio
import sys
import threading
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import settings
from tests.db_guard import (
    EXIT_CODE,
    SETUP,
    UnsafeTestDatabase,
    assert_test_url,
    check_test_database_url,
    guarded_engine,
)

# ---- the guard: before anything can build an engine -----------------------------------------

TEST_DATABASE_URL: URL


def pytest_configure(config: pytest.Config) -> None:
    """Runs before collection, so before any test module, fixture or engine exists. A
    UsageError stops the whole run with exit code 4 and the message."""
    global TEST_DATABASE_URL
    if "app.db.session" in sys.modules:  # its engine would already hold DATABASE_URL
        raise pytest.UsageError(
            "Tests stopped: app.db.session was imported before the test database guard ran."
        )
    try:
        TEST_DATABASE_URL = check_test_database_url(
            settings.test_database_url, settings.database_url
        )
    except UnsafeTestDatabase as exc:
        raise pytest.UsageError(str(exc)) from None
    settings.database_url = TEST_DATABASE_URL.render_as_string(hide_password=False)


def pytest_report_header() -> str:
    return f"test database: {TEST_DATABASE_URL.render_as_string(hide_password=True)}"


# The sample project is data for the indexing tests, not tests to run.
collect_ignore_glob = ["fixtures/*"]
BACKEND_DIR = Path(__file__).resolve().parents[1]


def get_test_database_url() -> URL:
    assert_test_url(TEST_DATABASE_URL)
    return TEST_DATABASE_URL


@pytest.fixture(scope="session", autouse=True)
def app_engine_is_the_test_database() -> None:
    """Checked again once the app is imported: its engine must point at the test database."""
    from app.db.session import engine

    assert_test_url(engine.url)


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
    """Alembic aimed at the test database only (downgrade tests drop every table there)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    rendered = get_test_database_url().render_as_string(hide_password=False)
    config.set_main_option("sqlalchemy.url", rendered.replace("%", "%%"))
    return config


def alembic_run(action: str, revision: str) -> None:
    run_in_thread(lambda: getattr(command, action)(alembic_config(), revision))


async def _ping_test_database() -> None:
    engine = guarded_engine(get_test_database_url(), poolclass=NullPool,
                            connect_args={"timeout": 5})  # fmt: skip
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


def _database_missing(exc: BaseException) -> bool:
    # asyncpg's InvalidCatalogNameError, wrapped twice by SQLAlchemy (DBAPIError, then the
    # adapter's Error), so walk the whole cause chain.
    seen: BaseException | None = exc
    while seen is not None:
        if type(seen).__name__ == "InvalidCatalogNameError":
            return True
        seen = seen.__cause__ or seen.__context__
    return False


@pytest.fixture(scope="session")
def migrated_database() -> URL:
    """Migrate the test database to head. Skips if PostgreSQL is down; stops the run if the
    test database doesn't exist (the tests never create one)."""
    try:
        run_in_thread(lambda: asyncio.run(_ping_test_database()))
    except (OSError, TimeoutError) as exc:
        pytest.skip(f"PostgreSQL is not reachable: {type(exc).__name__}")
    except Exception as exc:
        if _database_missing(exc):
            pytest.exit(f"The test database does not exist.\n\n{SETUP}", returncode=EXIT_CODE)
        raise
    alembic_run("upgrade", "head")
    return get_test_database_url()


@pytest.fixture(autouse=True)
def fake_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """pytest's temp folders sit under the real home's AppData on Windows, which the source
    folder check refuses. Tests get a separate empty home folder instead."""
    from app.modules.rag import source

    home = tmp_path_factory.mktemp("home")
    monkeypatch.setattr(source, "user_home", lambda: home)
    return home


@pytest.fixture(autouse=True)
def test_master_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """A fresh, generated master key for every test. Never a real key."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "master_encryption_key", key)
    return key


@pytest.fixture
async def engine(migrated_database: URL) -> AsyncIterator[AsyncEngine]:
    engine = guarded_engine(migrated_database, poolclass=NullPool)
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
