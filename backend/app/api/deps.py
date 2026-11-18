"""Shared FastAPI dependencies: database session and current user.

Endpoints commit their own writes (`await session.commit()`); the session rolls back on error.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.repositories import UserRepository
from app.db.session import SessionLocal


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user_id(session: DbSession) -> uuid.UUID:
    """v0.1: every request runs as the default local user (D8). Auth replaces only this."""
    user = await UserRepository(session).get_default()
    if user is None:
        raise AppError(
            "The default local user doesn't exist. Run: python -m app.db.seed",
            code="not_seeded",
            status_code=503,
        )
    return user.id


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def get_session_factory() -> SessionFactory:
    """Opens new sessions for work that outlives the request handler: an SSE stream and its
    background tasks. Tests override it to hand out the test session."""
    return SessionLocal


SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]
