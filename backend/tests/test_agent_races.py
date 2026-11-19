"""Two requests on one agent run at the same moment, on separate database connections."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.projects.models import MemoryItem
from app.modules.workflow.models import RunStatus
from tests.committed_helpers import committed_world

pytestmark = pytest.mark.db


async def count_memory(world_session: object, project_id: uuid.UUID) -> int:
    async with world_session() as s:  # type: ignore[operator]
        return int(
            await s.scalar(select(func.count()).where(MemoryItem.project_id == project_id)) or 0
        )


@pytest.mark.parametrize("second", ["approve", "reject"])
async def test_two_decisions_at_once_one_wins(engine: AsyncEngine, second: str) -> None:
    async with committed_world(engine) as world:
        run_id = await world.add_run(RunStatus.WAITING_FOR_APPROVAL)
        bodies = {"approve": {"all": True}, "reject": {"reason": "Too big"}}
        async with world.client() as c:
            first, other = await asyncio.gather(
                c.post(f"/api/v1/agent-runs/{run_id}/approve", json=bodies["approve"]),
                c.post(f"/api/v1/agent-runs/{run_id}/{second}", json=bodies[second]),
            )
        codes = sorted([first.status_code, other.status_code])
        assert codes == [200, 409], (first.text, other.text)
        loser = first if first.status_code == 409 else other
        assert loser.json()["error"]["code"] == "agent_run_not_waiting"
        run = await world.run_status(run_id)
        saved = await count_memory(world.session, world.project_id)
        if run.status == RunStatus.APPROVED:
            assert saved == 4  # 3 tasks + 1 decision, saved once
            assert len(run.saved_item_ids) == 4
        else:
            assert run.status == RunStatus.REJECTED and saved == 0
