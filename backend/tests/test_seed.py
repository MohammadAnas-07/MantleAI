import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import DEFAULT_LOCAL_USER_ID, User
from app.core.repositories import UserRepository
from app.db.seed import seed_default_user

pytestmark = pytest.mark.db


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    assert await seed_default_user(session) is True
    assert await seed_default_user(session) is False

    count = await session.scalar(select(func.count()).select_from(User))
    assert count == 1
    user = await UserRepository(session).get_default()
    assert user is not None
    assert user.id == DEFAULT_LOCAL_USER_ID
    assert user.is_local_default is True
