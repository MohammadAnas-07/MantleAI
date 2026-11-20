"""The test database guard: a test run can only ever reach a database whose name ends in _test,
taken from TEST_DATABASE_URL, and it stops before any connection when that is not the case."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import URL

from app.core.config import settings
from tests.db_guard import (
    EXIT_CODE,
    UnsafeTestDatabase,
    assert_test_url,
    check_test_database_url,
    guarded_engine,
)

BACKEND = Path(__file__).resolve().parents[1]
DEV = "postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/mantle"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_a_missing_setting_stops_with_instructions(raw: str | None) -> None:
    with pytest.raises(UnsafeTestDatabase) as info:
        check_test_database_url(raw, DEV)
    message = str(info.value)
    assert "TEST_DATABASE_URL is not set" in message
    assert "CREATE DATABASE mantle_test" in message  # how to fix it


@pytest.mark.parametrize(
    "raw",
    [
        DEV,  # the dev database itself
        "postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/mantle_dev",  # not *_test
        "postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/",  # no database name
        "postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/test_mantle",  # test, but not a suffix
        "sqlite+aiosqlite:///mantle_test",  # not PostgreSQL
        "not a url",
    ],
)
def test_a_non_test_database_is_refused(raw: str) -> None:
    with pytest.raises(UnsafeTestDatabase):
        check_test_database_url(raw, DEV)


def test_the_dev_database_is_refused_even_when_its_name_ends_in_test() -> None:
    dev = "postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/shop_test"
    with pytest.raises(UnsafeTestDatabase, match="same database"):
        check_test_database_url(dev, dev)


def test_a_test_database_is_accepted() -> None:
    url = check_test_database_url(
        "postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/mantle_test", DEV
    )
    assert url.database == "mantle_test"


def test_the_message_never_shows_the_password() -> None:
    with pytest.raises(UnsafeTestDatabase) as info:
        check_test_database_url("postgresql+asyncpg://mantle:hunter2pw@127.0.0.1:5433/mantle", DEV)
    assert "hunter2pw" not in str(info.value)


def test_engines_for_tests_refuse_a_non_test_database() -> None:
    with pytest.raises(UnsafeTestDatabase):
        assert_test_url(DEV)
    with pytest.raises(UnsafeTestDatabase):
        guarded_engine(DEV)  # refused before an engine exists


def test_the_app_engine_and_settings_point_at_the_test_database() -> None:
    from app.db.session import engine

    assert engine.url.database is not None and engine.url.database.endswith("_test")
    assert engine.url.database == settings.database_url.rsplit("/", 1)[-1]


def run_pytest_with(
    test_database_url: str, target: str = "tests/test_health.py"
) -> subprocess.CompletedProcess[str]:
    """A fresh pytest run of one test that would use the database, with this setting."""
    env = {**os.environ, "TEST_DATABASE_URL": test_database_url}
    return subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider"],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Port 1: even if the guard failed, nothing real could answer.
        ("postgresql+asyncpg://mantle:mantle@127.0.0.1:1/mantle", "must end in _test"),
        ("", "TEST_DATABASE_URL is not set"),
    ],
)
def test_a_whole_run_stops_before_any_test(value: str, expected: str) -> None:
    result = run_pytest_with(value)
    output = result.stdout + result.stderr
    assert result.returncode == EXIT_CODE, output
    assert expected in output
    assert "passed" not in output and "failed" not in output


@pytest.mark.db
def test_a_missing_test_database_stops_the_run(migrated_database: URL) -> None:
    """The server is up (the fixture would skip otherwise), but this _test database doesn't
    exist: the run stops with the create command instead of creating it."""
    missing = migrated_database.set(database="mantle_guard_missing_test")
    result = run_pytest_with(
        missing.render_as_string(hide_password=False),
        "tests/test_migrations.py::test_hnsw_cosine_index_exists",
    )
    output = result.stdout + result.stderr
    assert result.returncode == EXIT_CODE, output
    assert "The test database does not exist" in output
    assert "CREATE DATABASE mantle_test" in output
