"""Edge cases of agent runs and workflow state that the API tests don't reach directly."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.modules.llm.service import AuthFailed
from app.modules.rag.service import RetrievalOutcome
from app.modules.workflow import run_setup, runs, state
from app.modules.workflow.models import AgentRun, RunStatus, RunType
from tests.agent_helpers import AgentWorld, gap_report, make_agent_world, plan, review
from tests.api_helpers import api_client
from tests.conversation_helpers import session_factory

pytestmark = pytest.mark.db


@pytest.fixture
async def world(session: AsyncSession) -> AgentWorld:
    return await make_agent_world(session)


@pytest.fixture
async def client(session: AsyncSession, world: AgentWorld) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(session, world.gateway, world.user_id) as c:
        yield c


async def start_plan(client: httpx.AsyncClient, world: AgentWorld, **extra: Any) -> dict[str, Any]:
    world.script.say("planner", plan())
    world.script.say("reviewer", review())
    r = await client.post(f"/api/v1/projects/{world.project_id}/agent-runs", json={
        "run_type": "plan", "model_id": str(world.model_id),
        "requirement_id": str(world.memory["req_login"]), **extra,
    })  # fmt: skip
    assert r.status_code == 202, r.text
    got = await client.get(f"/api/v1/agent-runs/{r.json()['id']}")
    return dict(got.json())


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (AuthFailed("bad key"), {"code": "code_context_failed", "error_code": "auth_failed"}),
        (RuntimeError("database down"), {"code": "code_context_failed"}),
        (RetrievalOutcome([], {"code": "needs_reindex", "message": "m", "details": {}}),
         {"code": "needs_reindex", "message": "m", "details": {}}),
    ],
)  # fmt: skip
async def test_code_context_problems_only_warn(
    client: httpx.AsyncClient, world: AgentWorld, monkeypatch: pytest.MonkeyPatch,
    outcome: Any, expected: dict[str, Any],
) -> None:  # fmt: skip
    async def retrieve(*_: Any, **__: Any) -> RetrievalOutcome:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(runs, "retrieve_for_context", retrieve)
    body = await start_plan(client, world, use_code_context=True)
    assert body["status"] == "waiting_for_approval"
    assert body["warnings"] == [expected]


async def test_memory_that_does_not_fit_is_trimmed_with_a_warning(
    client: httpx.AsyncClient, world: AgentWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "agent_memory_max_share", 0.0001)
    body = await start_plan(client, world)
    assert body["status"] == "waiting_for_approval"
    assert body["warnings"][0]["code"] == "memory_trimmed" and body["warnings"][0]["count"] >= 1
    world.script.say("gap_finder", gap_report())
    r = await client.post(f"/api/v1/projects/{world.project_id}/gap-finder",
                          json={"model_id": str(world.model_id)})  # fmt: skip
    assert r.json()["warnings"][0]["code"] == "memory_trimmed"


async def test_long_text_from_the_model_is_invalid(
    client: httpx.AsyncClient, world: AgentWorld
) -> None:
    long = gap_report()
    long["missing_steps"][0]["explanation"] = "x" * 5000
    world.script.say("gap_finder", json.dumps(long))
    r = await client.post(f"/api/v1/projects/{world.project_id}/gap-finder",
                          json={"model_id": str(world.model_id)})  # fmt: skip
    assert r.status_code == 502 and "at most 4000" in r.json()["error"]["message"]


async def test_a_crash_in_the_job_fails_the_run_and_logs_the_type_only(
    session: AsyncSession, world: AgentWorld, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:  # fmt: skip
    run = await runs.start_run(session, world.gateway, world.user_id, world.project_id,
                               run_type=RunType.REVIEW, model_id=world.model_id)  # fmt: skip
    await session.commit()

    async def crash(*_: Any) -> None:
        raise ValueError("memory text: Users can log in")

    monkeypatch.setattr(runs, "_execute", crash)
    await runs.run_agent_job(session_factory(session), world.gateway, world.user_id, run.id)
    await session.refresh(run)
    assert (run.status, run.error) == ("failed", "internal_error")
    assert "type=ValueError" in caplog.text and "Users can log in" not in caplog.text
    # A second start of the same job does nothing: the run is no longer queued.
    await runs.run_agent_job(session_factory(session), world.gateway, world.user_id, run.id)
    await runs.run_agent_job(session_factory(session), world.gateway, world.user_id, uuid.uuid4())


async def test_two_runs_inserted_at_once_one_gets_409(
    session: AsyncSession, world: AgentWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    await runs.start_run(session, world.gateway, world.user_id, world.project_id,
                         run_type=RunType.REVIEW, model_id=world.model_id)  # fmt: skip

    async def nothing_active(*_: Any) -> None:
        return None  # as if the other insert had not committed yet when we checked

    monkeypatch.setattr(run_setup, "active_run", nothing_active)
    with pytest.raises(AppError) as info:
        await runs.start_run(session, world.gateway, world.user_id, world.project_id,
                             run_type=RunType.REVIEW, model_id=world.model_id)  # fmt: skip
    assert info.value.code == "agent_run_in_progress"
    assert info.value.status_code == 409


async def test_first_access_race_uses_the_other_row(
    session: AsyncSession, world: AgentWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await state.get_or_create(session, world.user_id, world.project_id)
    original = state._load
    calls = 0

    async def missing_first(*args: Any) -> Any:
        nonlocal calls
        calls += 1
        return None if calls == 1 else await original(*args)

    monkeypatch.setattr(state, "_load", missing_first)
    again = await state.get_or_create(session, world.user_id, world.project_id)
    assert again.id == created.id and calls == 2


async def test_forced_approval_without_a_reason_is_refused_by_the_service(
    session: AsyncSession, world: AgentWorld
) -> None:
    with pytest.raises(AppError) as info:
        await state.approve(session, world.user_id, world.project_id, force=True, reason=None)
    assert info.value.code == "reason_required"


async def test_runs_list_shows_only_plan_and_review(
    client: httpx.AsyncClient, session: AsyncSession, world: AgentWorld
) -> None:
    session.add(AgentRun(user_id=world.user_id, project_id=world.project_id,
                         run_type=RunType.GAP_FINDER, status=RunStatus.COMPLETED,
                         model_id=world.model_id, prompt_version="gap_finder_v1"))  # fmt: skip
    await session.flush()
    r = await client.get(f"/api/v1/projects/{world.project_id}/agent-runs")
    assert r.json()["items"] == []


async def test_drafts_respect_the_memory_limit_and_valid_dependencies(
    session: AsyncSession, world: AgentWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.projects.repository import MemoryItemRepository
    from app.modules.projects.service import DraftTask, add_agent_drafts

    async def save(tasks: list[DraftTask]) -> None:
        await add_agent_drafts(session, world.user_id, world.project_id, agent_run_id=None,
                               stage_key=None, tasks=tasks, decisions=[])  # type: ignore[arg-type]  # fmt: skip

    before = len(await MemoryItemRepository(session, world.user_id).in_project(world.project_id))
    with pytest.raises(AppError) as info:
        await save([DraftTask("A", "", "high", (5,))])
    assert info.value.code == "invalid_draft"
    monkeypatch.setattr(settings, "memory_max_items_per_kind", 1)  # the project has 1 task
    with pytest.raises(AppError) as info:
        await save([DraftTask("B", "", "low")])
    assert info.value.code == "memory_limit_reached"
    after = len(await MemoryItemRepository(session, world.user_id).in_project(world.project_id))
    assert after == before
