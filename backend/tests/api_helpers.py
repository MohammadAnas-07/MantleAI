"""Helpers for API tests: an httpx client bound to the test session, a user and a gateway."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db
from app.main import app
from app.modules.llm.gateway import Gateway
from app.modules.llm.service import get_gateway


@asynccontextmanager
async def api_client(
    session: AsyncSession, gateway: Gateway, user_id: uuid.UUID | None
) -> AsyncIterator[httpx.AsyncClient]:
    """A client whose requests use `session`, run as `user_id` and call `gateway`.

    With `user_id=None` the real current-user dependency runs (the seeded default user).
    """

    async def _db() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_gateway] = lambda: gateway
    if user_id is not None:
        app.dependency_overrides[get_current_user_id] = lambda: user_id
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
