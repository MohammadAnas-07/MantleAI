"""Minimal project endpoints, so conversations can be created through the API.
Update, archive, delete and memory CRUD come in `feat/project-memory`."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserId, DbSession
from app.modules.projects import service

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None


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
