"""Helpers for API tests: an httpx client bound to the test session, a user and a gateway."""

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db, get_session_factory
from app.main import app
from app.modules.llm.gateway import Gateway
from app.modules.llm.service import get_gateway


def override(session: AsyncSession, gateway: Gateway, user_id: uuid.UUID | None) -> None:
    async def _db() -> AsyncIterator[AsyncSession]:
        yield session

    @asynccontextmanager
    async def _factory() -> AsyncIterator[AsyncSession]:
        yield session  # streams and background tasks share the test transaction

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_session_factory] = lambda: _factory
    app.dependency_overrides[get_gateway] = lambda: gateway
    if user_id is not None:
        app.dependency_overrides[get_current_user_id] = lambda: user_id


@asynccontextmanager
async def api_client(
    session: AsyncSession, gateway: Gateway, user_id: uuid.UUID | None
) -> AsyncIterator[httpx.AsyncClient]:
    """A client whose requests use `session`, run as `user_id` and call `gateway`.

    With `user_id=None` the real current-user dependency runs (the seeded default user).
    """
    override(session, gateway, user_id)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events
