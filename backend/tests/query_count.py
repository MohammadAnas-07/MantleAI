"""Count the SQL statements sent while a block runs (for N+1 checks on list endpoints)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine


@contextmanager
def count_queries(engine: AsyncEngine) -> Iterator[list[str]]:
    """The statements (text only) run on `engine` inside the block, savepoints excluded."""
    statements: list[str] = []

    def before(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE", "ROLLBACK TO")):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)
