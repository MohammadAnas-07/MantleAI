"""A run left "running" by a job that died while the server stayed up (separate database
connections, committed data cleaned up after each test)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.workflow.models import AgentRun, RunStatus, RunType
from tests.committed_helpers import Committed, committed_world

pytestmark = pytest.mark.db


def runs_url(world: Committed) -> str:
    return f"/api/v1/projects/{world.project_id}/agent-runs"


def review_body(world: Committed) -> dict[str, str]:
    return {"run_type": "review", "model_id": str(world.model_id)}


async def test_a_run_left_running_by_a_dead_job_can_be_cancelled(engine: AsyncEngine) -> None:
    """A job that died without a restart (its process is still up) leaves `running` behind and
    blocks the project. Once it is older than AGENT_RUN_STALE_SECONDS, a cancel ends it."""
    async with committed_world(engine) as world:
        run_id = await world.add_run(RunStatus.RUNNING, RunType.REVIEW)
        async with world.session() as s:
            await s.execute(update(AgentRun).where(AgentRun.id == run_id).values(
                started_at=datetime.now(UTC) - timedelta(hours=1)))  # fmt: skip
            await s.commit()
        async with world.client() as c:
            blocked = await c.post(runs_url(world), json=review_body(world))
            assert blocked.status_code == 409
            cancel = await c.post(f"/api/v1/agent-runs/{run_id}/cancel", json={})
            assert cancel.status_code == 200 and cancel.json()["status"] == "cancelled"
            again = await c.post(runs_url(world), json=review_body(world))
        assert again.status_code == 202, again.text


async def test_a_fresh_running_run_is_not_cancelled_at_once(engine: AsyncEngine) -> None:
    """A live job still decides: a recent running run only gets the cancel request."""
    async with committed_world(engine) as world:
        run_id = await world.add_run(RunStatus.RUNNING, RunType.REVIEW)
        async with world.session() as s:
            await s.execute(update(AgentRun).where(AgentRun.id == run_id).values(
                started_at=datetime.now(UTC)))  # fmt: skip
            await s.commit()
        async with world.client() as c:
            cancel = await c.post(f"/api/v1/agent-runs/{run_id}/cancel", json={})
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "running" and cancel.json()["cancel_requested_at"]
