"""The tricky memory rules, at the service level: task dependency cycles, the supersede chain,
restoring a decision when its replacement is deleted."""

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFound
from app.modules.projects import memory_service as memory
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import MemoryItemCreate, MemoryItemPatch, SupersedeIn
from tests.graph import make_user

pytestmark = pytest.mark.db


@pytest.fixture
async def ctx(session: AsyncSession) -> dict[str, uuid.UUID]:
    user = await make_user(session, "Rina")
    projects = ProjectRepository(session, user)
    one = await projects.add(name="One")
    two = await projects.add(name="Two")
    return {"user": user, "p1": one.id, "p2": two.id}


async def new(session: AsyncSession, ctx: dict[str, uuid.UUID], kind: str, title: str,
              project: str = "p1", **fields: Any) -> uuid.UUID:  # fmt: skip
    item = await memory.create_item(
        session, ctx["user"], ctx[project], MemoryItemCreate(kind=kind, title=title, **fields)
    )
    return item.id


async def depend(session: AsyncSession, ctx: dict[str, uuid.UUID], task: uuid.UUID,
                 on: uuid.UUID) -> bool:  # fmt: skip
    return await memory.add_dependency(session, ctx["user"], task, on)


def code(info: pytest.ExceptionInfo[AppError]) -> tuple[int, str]:
    return info.value.status_code, info.value.code


# ---- task dependencies -----------------------------------------------------------------------


async def test_task_cannot_depend_on_itself(session: AsyncSession, ctx: dict) -> None:
    a = await new(session, ctx, "task", "A")
    with pytest.raises(AppError) as info:
        await depend(session, ctx, a, a)
    assert code(info) == (422, "invalid_dependency")


async def test_task_cannot_depend_on_another_projects_task(
    session: AsyncSession, ctx: dict
) -> None:
    a = await new(session, ctx, "task", "A")
    other = await new(session, ctx, "task", "Other", project="p2")
    with pytest.raises(NotFound):
        await depend(session, ctx, a, other)


async def test_only_tasks_have_dependencies(session: AsyncSession, ctx: dict) -> None:
    a = await new(session, ctx, "task", "A")
    decision = await new(session, ctx, "decision", "D")
    with pytest.raises(AppError) as info:
        await depend(session, ctx, a, decision)
    assert code(info) == (422, "invalid_dependency")


async def test_direct_cycle_is_rejected(session: AsyncSession, ctx: dict) -> None:
    a = await new(session, ctx, "task", "A")
    b = await new(session, ctx, "task", "B")
    assert await depend(session, ctx, a, b) is True
    with pytest.raises(AppError) as info:
        await depend(session, ctx, b, a)
    assert code(info) == (409, "dependency_cycle")


async def test_long_cycle_is_rejected(session: AsyncSession, ctx: dict) -> None:
    tasks = [await new(session, ctx, "task", f"T{i}") for i in range(12)]
    for first, second in zip(tasks, tasks[1:], strict=False):
        await depend(session, ctx, first, second)  # T0 -> T1 -> ... -> T11
    with pytest.raises(AppError) as info:
        await depend(session, ctx, tasks[-1], tasks[0])
    assert code(info) == (409, "dependency_cycle")
    # A diamond is fine: T0 -> T5 adds no cycle.
    assert await depend(session, ctx, tasks[0], tasks[5]) is True


async def test_duplicate_link_is_ignored(session: AsyncSession, ctx: dict) -> None:
    a = await new(session, ctx, "task", "A")
    b = await new(session, ctx, "task", "B")
    assert await depend(session, ctx, a, b) is True
    assert await depend(session, ctx, a, b) is False  # already there: no change, no error
    [view] = await memory.describe(
        session, ctx["user"], [await memory.get_item(session, ctx["user"], a)]
    )
    assert view.depends_on_ids == [b]


async def test_is_blocked_and_delete_cleans_links(session: AsyncSession, ctx: dict) -> None:
    a = await new(session, ctx, "task", "A")
    b = await new(session, ctx, "task", "B")
    await depend(session, ctx, a, b)

    async def view(item_id: uuid.UUID) -> Any:
        [out] = await memory.describe(
            session, ctx["user"], [await memory.get_item(session, ctx["user"], item_id)]
        )
        return out

    assert (await view(a)).is_blocked is True
    # Marking a blocked task done is allowed.
    await memory.update_item(session, ctx["user"], a, MemoryItemPatch(status="done"))
    await memory.update_item(session, ctx["user"], b, MemoryItemPatch(status="done"))
    assert (await view(a)).is_blocked is False

    await memory.delete_item(session, ctx["user"], b)
    assert (await view(a)).depends_on_ids == []


# ---- decisions: supersede ------------------------------------------------------------------


async def test_supersede_with_a_new_decision(session: AsyncSession, ctx: dict) -> None:
    old = await new(session, ctx, "decision", "Use MySQL", body="MySQL 8")
    newer = await memory.supersede(
        session, ctx["user"], old,
        SupersedeIn.model_validate({"decision": {"title": "Use PostgreSQL", "why": "pgvector"}}),
    )  # fmt: skip
    old_item = await memory.get_item(session, ctx["user"], old)
    assert old_item.status == "superseded" and old_item.superseded_by_id == newer.id
    assert newer.status == "accepted"
    [view] = await memory.describe(session, ctx["user"], [newer])
    assert view.supersedes_ids == [old]


async def test_superseded_status_only_through_the_action(session: AsyncSession, ctx: dict) -> None:
    old = await new(session, ctx, "decision", "D")
    with pytest.raises(AppError) as info:
        await memory.update_item(session, ctx["user"], old, MemoryItemPatch(status="superseded"))
    assert code(info) == (422, "invalid_field")
    with pytest.raises(AppError):
        await new(session, ctx, "decision", "E", status="superseded")


async def test_cannot_supersede_itself(session: AsyncSession, ctx: dict) -> None:
    old = await new(session, ctx, "decision", "D")
    with pytest.raises(AppError) as info:
        await memory.supersede(session, ctx["user"], old, SupersedeIn(by_id=old))
    assert code(info) == (422, "invalid_supersede")


async def test_cannot_supersede_across_projects(session: AsyncSession, ctx: dict) -> None:
    old = await new(session, ctx, "decision", "D")
    other = await new(session, ctx, "decision", "Other", project="p2")
    with pytest.raises(NotFound):
        await memory.supersede(session, ctx["user"], old, SupersedeIn(by_id=other))


async def test_supersede_loop_is_rejected(session: AsyncSession, ctx: dict) -> None:
    a = await new(session, ctx, "decision", "A")
    b = await new(session, ctx, "decision", "B")
    c = await new(session, ctx, "decision", "C")
    await memory.supersede(session, ctx["user"], a, SupersedeIn(by_id=b))  # B replaces A
    await memory.supersede(session, ctx["user"], b, SupersedeIn(by_id=c))  # C replaces B
    # A -> B -> C -> A would be a loop: A and B are superseded, so they can't replace C.
    for loop_back in (a, b):
        with pytest.raises(AppError) as info:
            await memory.supersede(session, ctx["user"], c, SupersedeIn(by_id=loop_back))
        assert code(info) == (409, "supersede_loop")


async def test_two_step_loop_is_rejected(session: AsyncSession, ctx: dict) -> None:
    a = await new(session, ctx, "decision", "A")
    b = await new(session, ctx, "decision", "B")
    await memory.supersede(session, ctx["user"], a, SupersedeIn(by_id=b))  # B replaces A
    with pytest.raises(AppError) as info:
        await memory.supersede(session, ctx["user"], b, SupersedeIn(by_id=a))  # A replaces B?
    assert code(info) == (409, "supersede_loop")


async def test_double_supersede_is_409(session: AsyncSession, ctx: dict) -> None:
    old = await new(session, ctx, "decision", "D")
    await memory.supersede(session, ctx["user"], old, SupersedeIn.model_validate(
        {"decision": {"title": "E"}}))  # fmt: skip
    with pytest.raises(AppError) as info:
        await memory.supersede(session, ctx["user"], old, SupersedeIn.model_validate(
            {"decision": {"title": "F"}}))  # fmt: skip
    assert code(info) == (409, "already_superseded")


async def test_deleting_the_newer_decision_restores_the_older(
    session: AsyncSession, ctx: dict
) -> None:
    old = await new(session, ctx, "decision", "D")
    newer = await memory.supersede(session, ctx["user"], old, SupersedeIn.model_validate(
        {"decision": {"title": "E"}}))  # fmt: skip
    await memory.delete_item(session, ctx["user"], newer.id)
    restored = await memory.get_item(session, ctx["user"], old)
    assert restored.status == "accepted" and restored.superseded_by_id is None


async def test_superseded_decision_status_is_locked(session: AsyncSession, ctx: dict) -> None:
    old = await new(session, ctx, "decision", "D")
    await memory.supersede(session, ctx["user"], old, SupersedeIn.model_validate(
        {"decision": {"title": "E"}}))  # fmt: skip
    with pytest.raises(AppError) as info:
        await memory.update_item(session, ctx["user"], old, MemoryItemPatch(status="accepted"))
    assert code(info) == (409, "superseded_locked")
