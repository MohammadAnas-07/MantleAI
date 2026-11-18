"""Project endpoints that combine two modules: the project (projects) and its index status (rag).

They live in app/api, above the modules, so the projects module keeps depending on nothing
(ADR 0006). Listing projects runs a fixed number of queries, however many projects there are.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserId, DbSession
from app.modules.projects import service as projects
from app.modules.rag import service as rag

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    # Optional: the folder to index, checked like PUT /projects/{id}/source.
    root_path: str | None = Field(default=None, min_length=1, max_length=4096)


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    root_path: str | None
    indexed: bool
    last_indexed_at: datetime | None
    needs_reindex: bool
    reindex_reasons: list[str]


def _out(project: projects.ProjectInfo, status: rag.IndexStatus) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        root_path=project.root_path,
        indexed=status.indexed,
        last_indexed_at=status.last_indexed_at,
        needs_reindex=status.needs_reindex,
        reindex_reasons=list(status.reindex_reasons),
    )


@router.get("/projects")
async def list_projects(session: DbSession, user_id: CurrentUserId) -> list[ProjectOut]:
    rows = await projects.list_projects(session, user_id)
    statuses = await rag.index_status_many(session, user_id, rows)
    return [_out(p, statuses[p.id]) for p in rows]


@router.post("/projects", status_code=201)
async def create_project(
    body: ProjectCreate, session: DbSession, user_id: CurrentUserId
) -> ProjectOut:
    project = await projects.create_project(session, user_id, body.name, body.description)
    if body.root_path is not None:
        await rag.set_source(session, user_id, project.id, body.root_path)
        project = await projects.get_project(session, user_id, project.id)
    await session.commit()
    return _out(project, await rag.index_status(session, user_id, project.id))


@router.get("/projects/{project_id}")
async def get_project(
    project_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> ProjectOut:
    project = await projects.get_project(session, user_id, project_id)
    return _out(project, await rag.index_status(session, user_id, project_id))
