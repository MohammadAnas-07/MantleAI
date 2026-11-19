"""Workflow state, gates, transitions and events through the API. Test database, no LLM."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.deps import get_current_user_id, get_db
from app.core.config import settings
from app.core.models import User
from app.main import app
from app.modules.llm.fake import FakeProvider
from app.modules.llm.gateway import Gateway
from app.modules.projects.repository import MemoryItemRepository, ProjectRepository
from app.modules.workflow.models import ProjectWorkflow, WorkflowEvent
from tests.api_helpers import api_client
from tests.graph import make_user

pytestmark = pytest.mark.db

STAGES = [
    "requirements", "architecture", "technical_decisions", "task_breakdown",
    "implementation_plan",
]  # fmt: skip
REQUIRED = {
    "requirements": ["users_and_goal", "scope_out"],
    "architecture": ["components", "data_flow"],
    "technical_decisions": ["choices_have_reasons", "security_considered"],
    "task_breakdown": ["tasks_small", "acceptance_criteria"],
    "implementation_plan": ["order_and_dependencies", "test_plan"],
}


@pytest.fixture
async def user_id(session: AsyncSession) -> uuid.UUID:
    return await make_user(session, "Workflow")


@pytest.fixture
async def project_id(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    return (await ProjectRepository(session, user_id).add(name="Old project")).id


@pytest.fixture
async def client(session: AsyncSession, user_id: uuid.UUID) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(session, Gateway(FakeProvider()), user_id) as c:
        yield c


def path(project_id: uuid.UUID, suffix: str = "") -> str:
    return f"/api/v1/projects/{project_id}/workflow{suffix}"


async def tick_all(client: httpx.AsyncClient, project_id: uuid.UUID, stage: str) -> None:
    for item in REQUIRED[stage]:
        r = await client.post(path(project_id, "/checklist"),
                              json={"stage_id": stage, "item_id": item, "done": True})  # fmt: skip
        assert r.status_code == 200, r.text


async def add_memory(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, kind: str, status: str
) -> None:
    await MemoryItemRepository(session, user_id).add(
        project_id=project_id, kind=kind, title=f"A {kind}", status=status, body=""
    )


async def test_first_access_creates_state_for_an_existing_project(
    client: httpx.AsyncClient, session: AsyncSession, project_id: uuid.UUID
) -> None:
    assert (
        await session.scalar(
            select(ProjectWorkflow).where(ProjectWorkflow.project_id == project_id)
        )
        is None
    )
    r = await client.get(path(project_id))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "active" and body["current_stage_id"] == "requirements"
    assert [s["id"] for s in body["stages"]] == STAGES
    assert [s["status"] for s in body["stages"]] == ["current"] + ["pending"] * 4
    assert [e["action"] for e in body["events"]] == ["created"]
    first = body["stages"][0]
    assert not first["ready"]
    assert {u["id"] for u in first["unmet"]} == {"users_and_goal", "scope_out", "artifact_0"}
    # A second read finds the same row.
    again = (await client.get(path(project_id))).json()
    assert again["version"] == body["version"] and len(again["events"]) == 1


async def test_list_stage_definitions(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/workflow/stages")
    assert [s["id"] for s in r.json()] == STAGES


async def test_gates_block_approval_until_met(
    client: httpx.AsyncClient, session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> None:
    r = await client.post(path(project_id, "/approve"), json={})
    assert r.status_code == 409
    error = r.json()["error"]
    assert error["code"] == "stage_gate_unmet"
    assert {u["type"] for u in error["details"]["unmet"]} == {"checklist", "artifact"}

    await tick_all(client, project_id, "requirements")
    r = await client.post(path(project_id, "/approve"), json={})
    assert r.status_code == 409
    [unmet] = r.json()["error"]["details"]["unmet"]
    assert (unmet["type"], unmet["have"], unmet["need"]) == ("artifact", 0, 1)

    await add_memory(session, user_id, project_id, "requirement", "draft")
    r = await client.post(path(project_id, "/approve"), json={})
    assert r.status_code == 409  # a draft requirement doesn't count

    await add_memory(session, user_id, project_id, "requirement", "approved")
    r = await client.post(path(project_id, "/approve"), json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current_stage_id"] == "architecture"
    assert body["stages"][0]["status"] == "approved"


async def test_unticking_blocks_again(client: httpx.AsyncClient, project_id: uuid.UUID) -> None:
    await tick_all(client, project_id, "requirements")
    r = await client.post(path(project_id, "/checklist"),
                          json={"stage_id": "requirements", "item_id": "scope_out",
                                "done": False})  # fmt: skip
    stage = r.json()["stages"][0]
    assert {u["id"] for u in stage["unmet"]} == {"scope_out", "artifact_0"}
    assert [e["action"] for e in r.json()["events"]][-1] == "untick"


async def test_unknown_checklist_item_or_stage_is_422(
    client: httpx.AsyncClient, project_id: uuid.UUID
) -> None:
    r = await client.post(path(project_id, "/checklist"),
                          json={"stage_id": "requirements", "item_id": "nope"})  # fmt: skip
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_checklist_item"
    r = await client.post(path(project_id, "/checklist"),
                          json={"stage_id": "nope", "item_id": "x"})  # fmt: skip
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_stage_id"


async def test_force_needs_a_reason_and_is_recorded(
    client: httpx.AsyncClient, project_id: uuid.UUID
) -> None:
    for body in ({"force": True}, {"force": True, "reason": "   "}):
        r = await client.post(path(project_id, "/approve"), json=body)
        assert r.status_code == 422
    too_long = "x" * (settings.workflow_reason_max_length + 1)
    r = await client.post(path(project_id, "/approve"), json={"force": True, "reason": too_long})
    assert r.status_code == 422

    body = {"force": True, "reason": "  spike, no requirements yet  "}
    r = await client.post(path(project_id, "/approve"), json=body)
    assert r.status_code == 200
    event = r.json()["events"][-1]
    assert event["action"] == "approve" and event["forced"] is True
    assert event["reason"] == "spike, no requirements yet"  # trimmed
    assert {u["id"] for u in event["details"]["unmet"]} == {
        "users_and_goal", "scope_out", "artifact_0",
    }  # fmt: skip


async def test_skip_needs_a_reason(client: httpx.AsyncClient, project_id: uuid.UUID) -> None:
    r = await client.post(path(project_id, "/skip"), json={"reason": ""})
    assert r.status_code == 422
    r = await client.post(path(project_id, "/skip"), json={})
    assert r.status_code == 422
    r = await client.post(path(project_id, "/skip"), json={"reason": "done elsewhere"})
    assert r.status_code == 200
    body = r.json()
    assert body["current_stage_id"] == "architecture"
    assert body["stages"][0]["status"] == "skipped"
    assert body["events"][-1]["action"] == "skip"


async def test_all_stages_then_completed_then_reopen(
    client: httpx.AsyncClient, project_id: uuid.UUID
) -> None:
    for _ in STAGES:
        r = await client.post(path(project_id, "/skip"), json={"reason": "fast"})
        assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed" and body["current_stage_id"] is None
    assert [e["action"] for e in body["events"]][-2:] == ["skip", "completed"]

    for action in ("/approve", "/skip"):
        r = await client.post(path(project_id, action), json={"reason": "again"})
        assert r.status_code == 409 and r.json()["error"]["code"] == "workflow_completed"

    reopen = {"stage_id": "architecture", "reason": "new constraint"}
    r = await client.post(path(project_id, "/reopen"), json=reopen)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "active" and body["current_stage_id"] == "architecture"
    assert [s["status"] for s in body["stages"]] == ["skipped", "current"] + ["pending"] * 3


async def test_reopen_only_earlier_stages(client: httpx.AsyncClient, project_id: uuid.UUID) -> None:
    r = await client.post(path(project_id, "/reopen"),
                          json={"stage_id": "requirements", "reason": "x"})  # fmt: skip
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_an_earlier_stage"
    r = await client.post(path(project_id, "/reopen"), json={"stage_id": "requirements"})
    assert r.status_code == 422  # reason required


async def test_events_are_immutable(
    client: httpx.AsyncClient, session: AsyncSession, project_id: uuid.UUID
) -> None:
    await client.post(path(project_id, "/skip"), json={"reason": "fast"})
    event = await session.scalar(select(WorkflowEvent).where(WorkflowEvent.action == "skip"))
    assert event is not None
    event.reason = "changed"
    with pytest.raises(RuntimeError, match="append-only"):
        await session.flush()
    await session.rollback()
    # The database refuses it too, even without the ORM.
    with pytest.raises(DBAPIError, match="append-only"):
        async with session.begin_nested():
            await session.execute(update(WorkflowEvent).values(reason="changed"))


async def test_unknown_stored_stage_is_409_and_reset_fixes_it(
    client: httpx.AsyncClient, session: AsyncSession, project_id: uuid.UUID
) -> None:
    await client.get(path(project_id))
    await session.execute(
        update(ProjectWorkflow)
        .where(ProjectWorkflow.project_id == project_id)
        .values(current_stage_id="removed_stage", checklist={"removed_stage": ["a"]})
    )
    r = await client.get(path(project_id))
    assert r.status_code == 409
    error = r.json()["error"]
    assert error["code"] == "unknown_stage" and "reset" in error["message"]
    assert error["details"]["reset_path"].endswith("/workflow/reset")
    r = await client.post(path(project_id, "/approve"), json={})
    assert r.status_code == 409

    r = await client.post(path(project_id, "/reset"), json={"reason": "stages changed"})
    assert r.status_code == 200
    body = r.json()
    assert body["current_stage_id"] == "requirements"
    assert body["events"][-1]["details"]["from_stage_id"] == "removed_stage"


async def test_other_users_and_missing_projects_are_404(
    client: httpx.AsyncClient, session: AsyncSession, project_id: uuid.UUID
) -> None:
    other = await make_user(session, "Other")
    theirs = await ProjectRepository(session, other).add(name="Theirs")
    for project in (theirs.id, uuid.uuid4()):
        assert (await client.get(path(project))).status_code == 404
        r = await client.post(path(project, "/skip"), json={"reason": "x"})
        assert r.status_code == 404


# ---- two approvals at the same moment -------------------------------------------------------


async def test_two_simultaneous_approvals_one_wins(engine: AsyncEngine) -> None:
    """Real concurrency needs separate connections and committed data, so this test commits
    and cleans up after itself instead of using the rolled-back test session."""
    async with AsyncSession(engine, expire_on_commit=False) as setup:
        user = User(display_name="Race")
        setup.add(user)
        await setup.flush()
        project = await ProjectRepository(setup, user.id).add(name="Race")
        await setup.commit()
        user_id, project_id = user.id, project.id

    async def own_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_db] = own_session
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
            assert (await c.get(path(project_id))).status_code == 200
            body: dict[str, Any] = {"force": True, "reason": "race"}
            first, second = await asyncio.gather(
                c.post(path(project_id, "/approve"), json=body),
                c.post(path(project_id, "/approve"), json=body),
            )
            codes = sorted([first.status_code, second.status_code])
            assert codes == [200, 409]
            loser = first if first.status_code == 409 else second
            assert loser.json()["error"]["code"] == "workflow_changed"
            state = (await c.get(path(project_id))).json()
            assert state["current_stage_id"] == "architecture"  # moved exactly one stage
            assert [e["action"] for e in state["events"]].count("approve") == 1
    finally:
        app.dependency_overrides.clear()
        async with AsyncSession(engine) as cleanup:
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
            left = await cleanup.scalar(
                text("SELECT count(*) FROM projects WHERE id = :id"), {"id": project_id}
            )
            assert left == 0
