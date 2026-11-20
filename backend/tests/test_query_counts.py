"""Query counts and payloads of list and detail endpoints: no N+1 (audit A-013), bounded lists."""

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.agent_helpers import AgentWorld, gap_report, make_agent_world, plan, review
from tests.api_helpers import api_client
from tests.query_count import count_queries

pytestmark = pytest.mark.db


@pytest.fixture
async def world(session: AsyncSession) -> AgentWorld:
    return await make_agent_world(session)


@pytest.fixture
async def client(session: AsyncSession, world: AgentWorld) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(session, world.gateway, world.user_id) as c:
        yield c


async def add_plan_runs(client: httpx.AsyncClient, world: AgentWorld, n: int) -> None:
    for _ in range(n):
        world.script.say("planner", plan())
        world.script.say("reviewer", review())
        r = await client.post(f"/api/v1/projects/{world.project_id}/agent-runs", json={
            "run_type": "plan", "model_id": str(world.model_id),
            "requirement_id": str(world.memory["req_login"])})  # fmt: skip
        assert r.status_code == 202, r.text


async def add_gap_runs(client: httpx.AsyncClient, world: AgentWorld, n: int) -> None:
    for _ in range(n):
        world.script.say("gap_finder", gap_report())
        r = await client.post(f"/api/v1/projects/{world.project_id}/gap-finder",
                              json={"model_id": str(world.model_id)})  # fmt: skip
        assert r.status_code == 200, r.text


async def queries_for(engine: AsyncEngine, client: httpx.AsyncClient, url: str) -> int:
    with count_queries(engine) as statements:
        r = await client.get(url)
    assert r.status_code == 200, r.text
    return len(statements)


async def test_the_agent_run_list_costs_the_same_for_1_and_5_runs(
    engine: AsyncEngine, client: httpx.AsyncClient, world: AgentWorld
) -> None:
    url = f"/api/v1/projects/{world.project_id}/agent-runs"
    await add_plan_runs(client, world, 1)
    one = await queries_for(engine, client, url)
    await add_plan_runs(client, world, 4)
    five = await queries_for(engine, client, url)
    assert five == one, (one, five)
    assert one <= 5


async def test_the_gap_finder_list_costs_the_same_for_1_and_5_runs(
    engine: AsyncEngine, client: httpx.AsyncClient, world: AgentWorld
) -> None:
    url = f"/api/v1/projects/{world.project_id}/gap-finder"
    await add_gap_runs(client, world, 1)
    one = await queries_for(engine, client, url)
    await add_gap_runs(client, world, 4)
    five = await queries_for(engine, client, url)
    assert five == one, (one, five)
    assert one <= 5


async def test_the_agent_run_list_is_a_summary_without_drafts(
    client: httpx.AsyncClient, world: AgentWorld
) -> None:
    """The list shows status, type, model, tokens and cost; the plan, the review and every
    step's output come with GET /agent-runs/{id} only."""
    await add_plan_runs(client, world, 2)
    items = (await client.get(f"/api/v1/projects/{world.project_id}/agent-runs")).json()["items"]
    assert len(items) == 2
    for item in items:
        assert "result" not in item and "steps" not in item and "input" not in item
        assert {"id", "status", "run_type", "model_id", "cost_usd", "created_at"} <= set(item)
    detail = (await client.get(f"/api/v1/agent-runs/{items[0]['id']}")).json()
    assert detail["result"]["plan"]["tasks"] and len(detail["steps"]) == 2


async def test_the_run_detail_takes_a_fixed_number_of_queries(
    engine: AsyncEngine, client: httpx.AsyncClient, world: AgentWorld
) -> None:
    await add_plan_runs(client, world, 1)
    [item] = (await client.get(f"/api/v1/projects/{world.project_id}/agent-runs")).json()["items"]
    assert await queries_for(engine, client, f"/api/v1/agent-runs/{item['id']}") <= 3
