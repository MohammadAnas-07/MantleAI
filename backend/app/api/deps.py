"""Shared FastAPI dependencies: database session and current user.

Endpoints commit their own writes (`await session.commit()`); the session rolls back on error.
"""

import uuid
from collections.abc import AsyncIterator
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
