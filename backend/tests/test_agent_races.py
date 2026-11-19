"""Two requests on one agent run at the same moment, on separate database connections."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.projects.models import MemoryItem
from app.modules.workflow.models import AgentRun, RunStatus, RunType
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


async def test_cancel_while_the_job_picks_up_a_queued_run(engine: AsyncEngine) -> None:
    """The job has read the run as queued; the cancel commits before the job marks it
    running. The cancel must win."""
    from app.modules.llm.fake import FakeProvider
    from app.modules.llm.gateway import Gateway
    from app.modules.workflow import runs

    async with committed_world(engine) as world:
        run_id = await world.add_run(RunStatus.QUEUED, RunType.REVIEW)
        fake = FakeProvider()
        async with world.session() as job_session:
            # What the job saw when it started: the run, still queued.
            stale = await job_session.get(AgentRun, run_id)
            assert stale is not None and stale.status == RunStatus.QUEUED
            async with world.client() as c:
                r = await c.post(f"/api/v1/agent-runs/{run_id}/cancel", json={})
                assert r.status_code == 200 and r.json()["status"] == "cancelled"

            @asynccontextmanager
            async def same_session() -> AsyncIterator[AsyncSession]:
                yield job_session

            await runs.run_agent_job(same_session, Gateway(fake), world.user_id, run_id)
        final = await world.run_status(run_id)
        assert final.status == RunStatus.CANCELLED
        assert fake.calls == []
