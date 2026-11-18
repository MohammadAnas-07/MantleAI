"""Project and project-memory endpoints. Routes stay thin; the rules are in memory_service.

Project update, archive and delete are not built yet.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserId, DbSession
from app.modules.projects import memory_service as memory
from app.modules.projects import service
from app.modules.projects.models import MemoryItemKind, MemoryItemStatus
from app.modules.projects.schemas import (
    DependencyIn,
    MemoryItemCreate,
    MemoryItemOut,
    MemoryItemPatch,
    MemoryPage,
    SupersedeIn,
)

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None


class SupersedeOut(BaseModel):
    superseded: MemoryItemOut
    by: MemoryItemOut


def _out(project: service.ProjectInfo) -> ProjectOut:
    return ProjectOut(id=project.id, name=project.name, description=project.description)


@router.get("/projects")
async def list_projects(session: DbSession, user_id: CurrentUserId) -> list[ProjectOut]:
    return [_out(p) for p in await service.list_projects(session, user_id)]


@router.post("/projects", status_code=201)
async def create_project(
    body: ProjectCreate, session: DbSession, user_id: CurrentUserId
) -> ProjectOut:
    project = await service.create_project(session, user_id, body.name, body.description)
    await session.commit()
    return _out(project)


@router.get("/projects/{project_id}")
async def get_project(
    project_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> ProjectOut:
    return _out(await service.get_project(session, user_id, project_id))


# ---- memory --------------------------------------------------------------------------------


async def _view(session: DbSession, user_id: uuid.UUID, item_id: uuid.UUID) -> MemoryItemOut:
    [view] = await memory.describe(
        session, user_id, [await memory.get_item(session, user_id, item_id)]
    )
    return view


@router.get("/projects/{project_id}/memory")
async def list_memory(
    project_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    kind: Literal["requirement", "decision", "task"] | None = None,
    status: MemoryItemStatus | None = None,
    limit: Annotated[int, Query(ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemoryPage:
    """A page of memory items, ordered by created_at then id. `limit` is capped by
    MEMORY_PAGE_MAX (default 100)."""
    items, total = await memory.list_items(
        session, user_id, project_id,
        kind=MemoryItemKind(kind) if kind else None, status=status, limit=limit, offset=offset,
    )  # fmt: skip
    views = await memory.describe(session, user_id, items)
    return MemoryPage(items=views, total=total, limit=limit, offset=offset)


@router.post("/projects/{project_id}/memory", status_code=201)
async def create_memory(
    project_id: uuid.UUID, body: MemoryItemCreate, session: DbSession, user_id: CurrentUserId
) -> MemoryItemOut:
    item = await memory.create_item(session, user_id, project_id, body)
    await session.commit()
    return await _view(session, user_id, item.id)


@router.get("/memory/{item_id}")
async def get_memory(
    item_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> MemoryItemOut:
    return await _view(session, user_id, item_id)


@router.patch("/memory/{item_id}")
async def update_memory(
    item_id: uuid.UUID, body: MemoryItemPatch, session: DbSession, user_id: CurrentUserId
) -> MemoryItemOut:
    """Changes only the fields that are sent; last write wins."""
    await memory.update_item(session, user_id, item_id, body)
    await session.commit()
    return await _view(session, user_id, item_id)


@router.delete("/memory/{item_id}", status_code=204)
async def delete_memory(item_id: uuid.UUID, session: DbSession, user_id: CurrentUserId) -> Response:
    await memory.delete_item(session, user_id, item_id)
    await session.commit()
    return Response(status_code=204)


@router.post("/memory/{item_id}/supersede", status_code=201)
async def supersede_decision(
    item_id: uuid.UUID, body: SupersedeIn, session: DbSession, user_id: CurrentUserId
) -> SupersedeOut:
    """Replace a decision with a new one ({"decision": {...}}) or an existing one ({"by_id"})."""
    newer = await memory.supersede(session, user_id, item_id, body)
    await session.commit()
    return SupersedeOut(
        superseded=await _view(session, user_id, item_id),
        by=await _view(session, user_id, newer.id),
    )


@router.post("/memory/{item_id}/dependencies")
async def add_dependency(
    item_id: uuid.UUID, body: DependencyIn, session: DbSession, user_id: CurrentUserId
) -> MemoryItemOut:
    """The task depends on `depends_on_id`. Adding a link that exists changes nothing."""
    await memory.add_dependency(session, user_id, item_id, body.depends_on_id)
    await session.commit()
    return await _view(session, user_id, item_id)


@router.delete("/memory/{item_id}/dependencies/{depends_on_id}", status_code=204)
async def remove_dependency(
    item_id: uuid.UUID, depends_on_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> Response:
    await memory.remove_dependency(session, user_id, item_id, depends_on_id)
    await session.commit()
    return Response(status_code=204)
