"""Two profile builds at once, on two real database connections (committed data, cleaned up
after each test). The upsert on the unique project_id keeps one row with one build's facts."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.rag.models import IndexRun, IndexRunStatus, ProjectProfile
from app.modules.rag.repository import ProjectProfileRepository
from tests.test_run_races import committed_index_world

pytestmark = pytest.mark.db


def build(n: int) -> dict[str, object]:
    return {
        "languages": {f"lang{n}": n},
        "commands": [{"name": f"cmd{n}", "command": "x", "source": f"src{n}", "kind": "script"}],
        "layout": [{"path": f"dir{n}", "files": n}],
    }


async def test_two_builds_at_once_leave_one_whole_profile(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    async with committed_index_world(engine, tmp_path) as world:
        async with world.session() as s:
            runs = [IndexRun(user_id=world.user_id, project_id=world.project_id,
                             status=IndexRunStatus.SUCCEEDED, embedding_model_id=world.model_id)
                    for _ in range(2)]  # fmt: skip
            s.add_all(runs)
            await s.commit()
            run_ids = [r.id for r in runs]

        first_saved = asyncio.Event()

        async def save(n: int) -> None:
            async with world.session() as s:
                repo = ProjectProfileRepository(s, world.user_id)
                if n == 1:
                    await first_saved.wait()  # the other transaction holds the row
                await repo.save(world.project_id, run_ids[n], build(n), datetime.now(UTC))
                if n == 0:
                    first_saved.set()
                    await asyncio.sleep(0.2)  # keep it open while the second one waits
                await s.commit()

        await asyncio.wait_for(asyncio.gather(save(0), save(1)), timeout=10)
        async with world.session() as s:
            rows = list(await s.scalars(select(ProjectProfile).where(
                ProjectProfile.project_id == world.project_id)))  # fmt: skip
        assert len(rows) == 1
        row = rows[0]
        n = run_ids.index(row.index_run_id)
        assert n == 1  # the later commit wins
        assert row.languages == build(n)["languages"]
        assert row.commands == build(n)["commands"] and row.layout == build(n)["layout"]
