"""Create the default local user and the default model catalog. Safe to run any number of times.

Run from backend/:  python -m app.db.seed
"""

import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.models import DEFAULT_LOCAL_USER_ID, User

logger = logging.getLogger(__name__)


async def seed_default_user(session: AsyncSession) -> bool:
    """Insert the default local user if it is missing. Returns True if a row was created."""
    stmt = (
        insert(User)
        .values(id=DEFAULT_LOCAL_USER_ID, display_name="Local user", is_local_default=True)
        .on_conflict_do_nothing(index_elements=[User.id])
    )
    result = await session.execute(stmt)
    return result.rowcount == 1


async def main() -> None:
    from app.db.session import SessionLocal, engine
    from app.modules.llm.service import seed_default_models

    try:
        async with SessionLocal() as session:
            created = await seed_default_user(session)
            models_created = await seed_default_models(session)
            await session.commit()
    finally:
        await engine.dispose()
    if created:
        logger.info("Created the default local user (%s).", DEFAULT_LOCAL_USER_ID)
    else:
        logger.info("Default local user already exists.")
    logger.info("Added %d catalog model(s); existing models were left unchanged.", models_created)


if __name__ == "__main__":
    setup_logging(settings.log_level)
    asyncio.run(main())
