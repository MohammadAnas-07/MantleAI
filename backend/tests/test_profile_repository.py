"""The profile table keeps one row per project and filters by user (test database)."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.models import ProjectProfile
from app.modules.rag.repository import ProjectProfileRepository
from tests.rag_helpers import index_once, make_rag_world

pytestmark = pytest.mark.db


async def test_saving_twice_keeps_one_row_with_the_newest_facts(
    session: AsyncSession, tmp_path: Path
) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    world = await make_rag_world(session, tmp_path, name="Repo")
    run = await index_once(session, world)
    repo = ProjectProfileRepository(session, world.user_id)
    facts = {"languages": {"python": 1}, "commands": [{"name": "a", "command": "x",
                                                         "source": "package.json"}]}  # fmt: skip
    await repo.save(world.project_id, run.id, facts, datetime.now(UTC))
    await repo.save(world.project_id, run.id, {"languages": {"python": 2}}, datetime.now(UTC))
    rows = await session.scalar(select(func.count()).select_from(ProjectProfile).where(
        ProjectProfile.project_id == world.project_id))  # fmt: skip
    assert rows == 1
    profile = await repo.get_for_project(world.project_id)
    assert profile is not None and profile.languages == {"python": 2}
    assert profile.commands == []  # a field missing from a build is cleared, not kept


async def test_another_user_sees_no_profile(session: AsyncSession, tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n")
    mine = await make_rag_world(session, tmp_path, name="Mine")
    other = await make_rag_world(session, tmp_path, name="Other")
    run = await index_once(session, mine)
    await ProjectProfileRepository(session, mine.user_id).save(
        mine.project_id, run.id, {"languages": {"python": 1}}, datetime.now(UTC))  # fmt: skip
    assert await ProjectProfileRepository(session, other.user_id).get_for_project(
        mine.project_id) is None  # fmt: skip
