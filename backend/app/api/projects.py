"""Project endpoints that combine modules: the project (projects), its index status (rag) and
its default model (llm).

They live in app/api, above the modules, so the projects module keeps depending on nothing
(ADR 0006). Listing projects runs a fixed number of queries, however many projects there are.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.deps import CurrentUserId, DbSession
from app.core.errors import AppError
from app.modules.llm.service import get_chat_model
from app.modules.projects import service as projects
from app.modules.rag import service as rag

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    # Optional: the folder to index, checked like PUT /projects/{id}/source.
    root_path: str | None = Field(default=None, min_length=1, max_length=4096)


class ProjectPatch(BaseModel):
    """Only the fields sent change. `default_model_id: null` clears the default model."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    default_model_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> "ProjectPatch":
        if not self.model_fields_set:
            raise ValueError("send name or default_model_id")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name can't be null")
        return self


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    root_path: str | None
    default_model_id: uuid.UUID | None
    indexed: bool
    last_indexed_at: datetime | None
    needs_reindex: bool
    reindex_reasons: list[str]


class ProjectBusy(AppError):
    status_code = 409
    code = "index_in_progress"


def _out(project: projects.ProjectInfo, status: rag.IndexStatus) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        root_path=project.root_path,
        default_model_id=project.default_model_id,
        indexed=status.indexed,
        last_indexed_at=status.last_indexed_at,
        needs_reindex=status.needs_reindex,
        reindex_reasons=list(status.reindex_reasons),
    )


@router.get("/projects")
async def list_projects(session: DbSession, user_id: CurrentUserId) -> list[ProjectOut]:
    """All projects with their index status."""
    rows = await projects.list_projects(session, user_id)
    statuses = await rag.index_status_many(session, user_id, rows)
    return [_out(p, statuses[p.id]) for p in rows]


@router.post("/projects", status_code=201)
async def create_project(
    body: ProjectCreate, session: DbSession, user_id: CurrentUserId
) -> ProjectOut:
    """Create a project, optionally with its source folder."""
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
    """One project with its index status."""
    project = await projects.get_project(session, user_id, project_id)
    return _out(project, await rag.index_status(session, user_id, project_id))


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: uuid.UUID, body: ProjectPatch, session: DbSession, user_id: CurrentUserId
) -> ProjectOut:
    """Rename the project or set its default chat model. An unknown or disabled model is 422
    `model_unavailable`; a model without a saved key is allowed (the UI warns)."""
    changes = body.model_dump(include=body.model_fields_set)
    if changes.get("default_model_id") is not None:
        await get_chat_model(session, changes["default_model_id"])
    project = await projects.update_project(session, user_id, project_id, **changes)
    await session.commit()
    return _out(project, await rag.index_status(session, user_id, project_id))


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> Response:
    """Delete the project and all its data. 409 while an index run is queued or running."""
    await projects.get_project(session, user_id, project_id)
    if await rag.has_active_run(session, user_id, project_id):
        raise ProjectBusy("Cancel the running index first, then delete the project.")
    await projects.delete_project(session, user_id, project_id)
    await session.commit()
    return Response(status_code=204)
