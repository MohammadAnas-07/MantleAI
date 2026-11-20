"""The test database guard.

A test run may only reach a dedicated test database: the one named in TEST_DATABASE_URL, whose
database name ends in `_test` and differs from the development database. `conftest.py` checks
it before any test module is imported and stops the whole run otherwise, so nothing can connect,
write, truncate or drop anywhere else. It fails closed: a missing setting stops the run too; it
never falls back to DATABASE_URL. Every engine a test builds goes through `guarded_engine`, so a
new helper can't skip the check.
"""

from typing import Any

from sqlalchemy import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# pytest's "usage error" code: the run was set up wrongly, no test ran.
EXIT_CODE = 4
SUFFIX = "_test"

CREATE_COMMAND = (
    "docker exec mantleai-db-1 psql -U mantle -d postgres "
    '-c "CREATE DATABASE mantle_test OWNER mantle;"'
)
SETUP = f"""\
Set TEST_DATABASE_URL to a database whose name ends in _test, for example in backend/.env:

    TEST_DATABASE_URL=postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/mantle_test

If that database doesn't exist yet, create it once (Docker must be running):

    {CREATE_COMMAND}

The tests create the tables themselves (alembic upgrade head on mantle_test)."""


class UnsafeTestDatabase(Exception):
    """The test database setting is missing or names a database that isn't a test database."""


def _refuse(reason: str) -> UnsafeTestDatabase:
    return UnsafeTestDatabase(
        f"Tests stopped before connecting to any database: {reason}\n\n{SETUP}"
    )


def _name(url: URL) -> str:
    """Host, port and database, never the password."""
    return url.render_as_string(hide_password=True)


def check_test_database_url(raw: str | None, dev_url: str) -> URL:
    """The test database URL, or UnsafeTestDatabase saying why it can't be used."""
    if raw is None or not raw.strip():
        raise _refuse("TEST_DATABASE_URL is not set.")
    try:
        url = make_url(raw.strip())
    except ArgumentError:
        raise _refuse("TEST_DATABASE_URL is not a database URL.") from None
    if url.get_backend_name() != "postgresql":
        raise _refuse(f"TEST_DATABASE_URL must be a PostgreSQL URL, not {url.drivername}.")
    database = url.database or ""
    if not database.endswith(SUFFIX) or database == SUFFIX:
        raise _refuse(
            f"the database name in TEST_DATABASE_URL must end in {SUFFIX} ({_name(url)})."
        )
    try:
        dev = make_url(dev_url)
    except ArgumentError:
        dev = None
    if dev is not None and (dev.host, dev.port, dev.database) == (url.host, url.port, database):
        raise _refuse(f"TEST_DATABASE_URL is the same database as DATABASE_URL ({_name(url)}).")
    return url


def assert_test_url(url: str | URL) -> None:
    """Raise UnsafeTestDatabase unless `url` names a *_test database."""
    parsed = make_url(url) if isinstance(url, str) else url
    database = parsed.database or ""
    if not database.endswith(SUFFIX) or database == SUFFIX:
        raise _refuse(f"a test tried to use {_name(parsed)}.")


def guarded_engine(url: str | URL, **kwargs: Any) -> AsyncEngine:
    """`create_async_engine` for tests: refuses anything but a test database."""
    assert_test_url(url)
    return create_async_engine(url, **kwargs)
