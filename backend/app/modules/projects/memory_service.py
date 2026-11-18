"""Project memory: requirements, decisions and tasks, written only by the user.

All rules live here; routes stay thin. Every query filters by user_id and project_id, and an
item of another user or another project is reported as not found (404), never as forbidden.
Concurrent edits are last-write-wins: there is no version check.
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, NotFound
from app.modules.projects.models import (
    DEFAULT_STATUS,
    PRIORITIES_BY_KIND,
    STATUSES_BY_KIND,
    MemoryItem,
    MemoryItemKind,
    MemoryItemPriority,
    MemoryItemSource,
    MemoryItemStatus,
)
from app.modules.projects.repository import (
    MemoryDependencyRepository,
    MemoryItemRepository,
    ProjectRepository,
)
from app.modules.projects.schemas import (
    MemoryItemCreate,
    MemoryItemOut,
    MemoryItemPatch,
    SupersedeIn,
)

logger = logging.getLogger(__name__)

DECISION_ONLY = ("why", "alternatives", "decided_at")
# A decision gets decided_at when it is created already decided.
_DECIDED = {MemoryItemStatus.ACCEPTED, MemoryItemStatus.REJECTED}


def invalid(field: str, message: str) -> AppError:
    return AppError(message, code="invalid_field", status_code=422, details={"field": field})


def conflict(code: str, message: str, **details: Any) -> AppError:
    return AppError(message, code=code, status_code=409, details=details)


# ---- lookups -------------------------------------------------------------------------------


async def _check_project(session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
    if await ProjectRepository(session, user_id).get(project_id) is None:
        raise NotFound("Project not found.")


async def get_item(session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> MemoryItem:
    item = await MemoryItemRepository(session, user_id).get(item_id)
    if item is None:
        raise NotFound("Memory item not found.")
    return item


async def _item_in(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, item_id: uuid.UUID
) -> MemoryItem:
    item = await MemoryItemRepository(session, user_id).get(item_id)
    if item is None or item.project_id != project_id:
        raise NotFound("Memory item not found in this project.")
    return item


async def list_items(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    kind: MemoryItemKind | None = None,
    status: MemoryItemStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[MemoryItem], int]:
    """One page, ordered by created_at then id, so pages never shuffle between calls."""
    await _check_project(session, user_id, project_id)
    if not 1 <= limit <= settings.memory_page_max:
        raise invalid("limit", f"limit must be between 1 and {settings.memory_page_max}.")
    if offset < 0:
        raise invalid("offset", "offset must not be negative.")
    return await MemoryItemRepository(session, user_id).page(
        project_id, kind=kind, status=status, limit=limit, offset=offset
    )


# ---- field rules per kind --------------------------------------------------------------------


def _check_fields(kind: MemoryItemKind, values: dict[str, Any], *, creating: bool) -> None:
    status = values.get("status")
    if status is not None:
        try:
            status = MemoryItemStatus(status)
        except ValueError:
            status = None
        if status is None or status not in STATUSES_BY_KIND[kind]:
            allowed = ", ".join(s.value for s in STATUSES_BY_KIND[kind] if s.value != "superseded")
            raise invalid("status", f"A {kind.value} status must be one of: {allowed}.")
        if status == MemoryItemStatus.SUPERSEDED:
            raise invalid("status", "Use the supersede action to supersede a decision.")
        values["status"] = status
    elif "status" in values and not creating:
        raise invalid("status", "status can't be null.")

    priority = values.get("priority")
    if priority is not None:
        allowed_priorities = PRIORITIES_BY_KIND[kind]
        if not allowed_priorities:
            raise invalid("priority", f"A {kind.value} has no priority.")
        try:
            values["priority"] = MemoryItemPriority(priority)
        except ValueError:
            values["priority"] = None
        if values["priority"] not in allowed_priorities:
            choices = ", ".join(p.value for p in allowed_priorities)
            raise invalid("priority", f"A {kind.value} priority must be one of: {choices}.")

    if kind != MemoryItemKind.DECISION:
        for field in DECISION_ONLY:
            if values.get(field) is not None:
                raise invalid(field, f"Only decisions have '{field}'.")


# ---- create, update, delete ------------------------------------------------------------------


async def create_item(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, data: MemoryItemCreate
) -> MemoryItem:
    await _check_project(session, user_id, project_id)
    kind = MemoryItemKind(data.kind)
    values = data.model_dump(exclude={"kind"})
    _check_fields(kind, values, creating=True)

    items = MemoryItemRepository(session, user_id)
    limit = settings.memory_max_items_per_kind
    if await items.count(project_id, kind) >= limit:
        raise conflict(
            "memory_limit_reached",
            f"This project already has {limit} {kind.value}s, the maximum. Delete some first.",
            kind=kind.value,
            limit=limit,
        )
    status = values.pop("status") or DEFAULT_STATUS[kind]
    if kind == MemoryItemKind.DECISION and status in _DECIDED and values["decided_at"] is None:
        values["decided_at"] = datetime.now(UTC)
    values["body"] = values["body"] or ""
    item = await items.add(
        project_id=project_id, kind=kind, status=status, source=MemoryItemSource.USER, **values
    )
    logger.info("memory item created id=%s kind=%s project=%s", item.id, kind.value, project_id)
    return item


async def update_item(
    session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, patch: MemoryItemPatch
) -> MemoryItem:
    """Change only the fields that were sent. Last write wins."""
    item = await get_item(session, user_id, item_id)
    values = patch.changes()
    _check_fields(item.kind, values, creating=False)
    if "body" in values and values["body"] is None:
        values["body"] = ""
    if "status" in values and item.status == MemoryItemStatus.SUPERSEDED:
        raise conflict(
            "superseded_locked",
            "A superseded decision keeps its status. Delete the newer decision to restore it.",
            superseded_by_id=str(item.superseded_by_id),
        )
    updated = await MemoryItemRepository(session, user_id).update(item_id, **values)
    assert updated is not None
    logger.info("memory item updated id=%s fields=%s", item_id, ",".join(sorted(values)))
    return updated


async def delete_item(session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """Delete an item. Its dependency links go with it (ON DELETE CASCADE). Decisions it had
    superseded become accepted again."""
    item = await get_item(session, user_id, item_id)
    items = MemoryItemRepository(session, user_id)
    restored = await items.superseded_by(item.project_id, [item.id])
    for older in restored:
        await items.update(older.id, status=MemoryItemStatus.ACCEPTED, superseded_by_id=None)
    await items.delete(item.id)
    logger.info("memory item deleted id=%s restored=%d", item_id, len(restored))


# ---- decisions: supersede --------------------------------------------------------------------


async def supersede(
    session: AsyncSession, user_id: uuid.UUID, old_id: uuid.UUID, data: SupersedeIn
) -> MemoryItem:
    """Replace decision `old_id` with a new decision, or with an existing one (`by_id`).

    The old one becomes `superseded` and points at its replacement. Returns the replacement.
    """
    old = await get_item(session, user_id, old_id)
    if old.kind != MemoryItemKind.DECISION:
        raise AppError("Only decisions can be superseded.", code="invalid_supersede",
                       status_code=422)  # fmt: skip
    if old.status == MemoryItemStatus.SUPERSEDED:
        raise conflict("already_superseded", "This decision is already superseded.",
                       superseded_by_id=str(old.superseded_by_id))  # fmt: skip

    items = MemoryItemRepository(session, user_id)
    if data.by_id is not None:
        if data.by_id == old.id:
            raise AppError("A decision can't supersede itself.", code="invalid_supersede",
                           status_code=422)  # fmt: skip
        newer = await _item_in(session, user_id, old.project_id, data.by_id)
        if newer.kind != MemoryItemKind.DECISION:
            raise AppError("Only a decision can supersede a decision.", code="invalid_supersede",
                           status_code=422)  # fmt: skip
        # Every decision that `old` replaced, directly or through a chain, is superseded. So
        # refusing a superseded replacement also rules out every loop (A -> B -> A).
        if newer.status == MemoryItemStatus.SUPERSEDED:
            raise conflict(
                "supersede_loop",
                "The replacement is itself superseded; that would make a loop or a broken chain.",
            )
    else:
        assert data.decision is not None
        newer = await create_item(
            session, user_id, old.project_id,
            MemoryItemCreate(kind="decision", **data.decision.model_dump()),
        )  # fmt: skip

    await items.update(old.id, status=MemoryItemStatus.SUPERSEDED, superseded_by_id=newer.id)
    logger.info("decision superseded id=%s by=%s", old.id, newer.id)
    return newer


# ---- tasks: dependencies -----------------------------------------------------------------------


async def add_dependency(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, depends_on_id: uuid.UUID
) -> bool:
    """Make `task_id` depend on `depends_on_id`. Returns False if the link already existed
    (a duplicate is ignored, not an error)."""
    task = await get_item(session, user_id, task_id)
    if task_id == depends_on_id:
        raise AppError("A task can't depend on itself.", code="invalid_dependency",
                       status_code=422)  # fmt: skip
    other = await _item_in(session, user_id, task.project_id, depends_on_id)
    if task.kind != MemoryItemKind.TASK or other.kind != MemoryItemKind.TASK:
        raise AppError("Only tasks can depend on tasks.", code="invalid_dependency",
                       status_code=422)  # fmt: skip

    links = MemoryDependencyRepository(session, user_id)
    if await links.find(task_id, depends_on_id) is not None:
        return False
    edges = await links.edges(task.project_id)
    if _reaches(edges, start=depends_on_id, target=task_id):
        raise conflict("dependency_cycle", "That dependency would make a cycle.",
                       task_id=str(task_id), depends_on_id=str(depends_on_id))  # fmt: skip
    await links.add(project_id=task.project_id, task_id=task_id, depends_on_id=depends_on_id)
    logger.info("dependency added task=%s depends_on=%s", task_id, depends_on_id)
    return True


def _reaches(
    edges: list[tuple[uuid.UUID, uuid.UUID]], *, start: uuid.UUID, target: uuid.UUID
) -> bool:
    """Is `target` reachable from `start` by following depends-on links? Iterative DFS, so a
    chain of any length works without recursion limits."""
    graph: dict[uuid.UUID, list[uuid.UUID]] = {}
    for task, dep in edges:
        graph.setdefault(task, []).append(dep)
    stack, seen = [start], set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(graph.get(node, []))
    return False


async def remove_dependency(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, depends_on_id: uuid.UUID
) -> None:
    task = await get_item(session, user_id, task_id)
    links = MemoryDependencyRepository(session, user_id)
    link = await links.find(task_id, depends_on_id)
    if link is None or link.project_id != task.project_id:
        raise NotFound("Dependency not found.")
    await links.delete(link.id)


# ---- views ---------------------------------------------------------------------------------


async def describe(
    session: AsyncSession, user_id: uuid.UUID, items: Sequence[MemoryItem]
) -> list[MemoryItemOut]:
    """API views of items: adds depends_on_ids, is_blocked and supersedes_ids."""
    by_project: dict[uuid.UUID, list[MemoryItem]] = {}
    for item in items:
        by_project.setdefault(item.project_id, []).append(item)

    out: dict[uuid.UUID, MemoryItemOut] = {}
    repo = MemoryItemRepository(session, user_id)
    links = MemoryDependencyRepository(session, user_id)
    for project_id, group in by_project.items():
        edges = await links.edges(project_id)
        deps: dict[uuid.UUID, list[uuid.UUID]] = {}
        for task, dep in edges:
            deps.setdefault(task, []).append(dep)
        needed = {d for item in group for d in deps.get(item.id, [])}
        status_of = {
            i.id: i.status for i in await repo.in_project(project_id, ids=needed)
        } if needed else {}  # fmt: skip
        older = await repo.superseded_by(project_id, [i.id for i in group])
        supersedes: dict[uuid.UUID, list[uuid.UUID]] = {}
        for o in sorted(older, key=lambda o: (o.created_at, o.id)):
            supersedes.setdefault(o.superseded_by_id, []).append(o.id)  # type: ignore[arg-type]

        for item in group:
            item_deps = sorted(deps.get(item.id, []), key=str)
            is_task = item.kind == MemoryItemKind.TASK
            out[item.id] = MemoryItemOut(
                id=item.id,
                project_id=item.project_id,
                kind=item.kind.value,
                title=item.title,
                body=item.body,
                status=item.status.value,
                priority=item.priority.value if item.priority else None,
                why=item.why,
                alternatives=item.alternatives,
                decided_at=item.decided_at,
                superseded_by_id=item.superseded_by_id,
                supersedes_ids=supersedes.get(item.id, []),
                depends_on_ids=item_deps,
                is_blocked=(
                    any(status_of.get(d) != MemoryItemStatus.DONE for d in item_deps)
                    if is_task
                    else None
                ),
                source=item.source.value,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
    return [out[item.id] for item in items]
