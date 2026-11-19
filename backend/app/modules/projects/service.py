"""Public interface of the projects module (rule 6).

Other modules read projects and project memory only through this file. Memory is written only by
the user through the projects endpoints (`memory_service.py`); nothing here calls an LLM.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.modules.projects.models import Project
from app.modules.projects.pinned import (
    DroppedPin,
    PinnedItem,
    PinnedSelection,
    pinned_block,
    select_pinned,
)
from app.modules.projects.repository import MemoryItemRepository, ProjectRepository

__all__ = [
    "DroppedPin",
    "MemoryRef",
    "PinnedItem",
    "PinnedSelection",
    "ProjectInfo",
    "create_project",
    "delete_project",
    "get_project",
    "list_projects",
    "memory_refs",
    "pinned_block",
    "pinned_selection",
    "set_root_path",
    "update_project",
]


@dataclass(frozen=True)
class ProjectInfo:
    id: uuid.UUID
    name: str
    description: str | None
    root_path: str | None = None  # the indexed folder; validated by the rag module
    default_model_id: uuid.UUID | None = None  # checked by the caller (projects calls no module)


@dataclass(frozen=True)
class MemoryRef:
    """A memory item as other modules may see it (read-only)."""

    id: uuid.UUID
    kind: str
    status: str
    priority: str | None
    title: str
    body: str

    @property
    def short_id(self) -> str:
        """The 8-character id shown in pinned memory lines."""
        return self.id.hex[:8]


def _info(project: Project) -> ProjectInfo:
    return ProjectInfo(
        project.id, project.name, project.description, project.root_path, project.default_model_id
    )


async def get_project(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> ProjectInfo:
    project = await ProjectRepository(session, user_id).get(project_id)
    if project is None:
        raise NotFound("Project not found.")
    return _info(project)


async def create_project(
    session: AsyncSession, user_id: uuid.UUID, name: str, description: str | None
) -> ProjectInfo:
    project = await ProjectRepository(session, user_id).add(name=name, description=description)
    return _info(project)


async def list_projects(session: AsyncSession, user_id: uuid.UUID) -> list[ProjectInfo]:
    rows = await ProjectRepository(session, user_id).list(archived_at=None, limit=500)
    return [_info(p) for p in rows]


async def update_project(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, **changes: object
) -> ProjectInfo:
    """Change `name` and/or `default_model_id` (None clears it). The caller has checked that
    the model exists; this module calls no other module."""
    unknown = set(changes) - {"name", "default_model_id"}
    if unknown:
        raise ValueError(f"can't change {sorted(unknown)}")
    await get_project(session, user_id, project_id)
    project = await ProjectRepository(session, user_id).update(project_id, **changes)
    assert project is not None
    return _info(project)


async def delete_project(session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
    """Delete the project; the database cascades to its memory, conversations, index and
    runs. Usage rows stay (their project link is set to null)."""
    await get_project(session, user_id, project_id)
    await ProjectRepository(session, user_id).delete(project_id)


async def set_root_path(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, root_path: str | None
) -> ProjectInfo:
    """Store the project's source folder. The caller (rag) has already checked the path; this
    module never touches the disk."""
    await get_project(session, user_id, project_id)
    project = await ProjectRepository(session, user_id).update(project_id, root_path=root_path)
    assert project is not None
    return _info(project)


async def pinned_selection(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    max_tokens: int,
    count: Callable[[str], int],
) -> PinnedSelection:
    """The project's pinned memory within `max_tokens`. The caller passes the token counter of
    the target model (projects calls no other module, so it can't count tokens itself)."""
    await get_project(session, user_id, project_id)
    rows = await MemoryItemRepository(session, user_id).in_project(project_id)
    return select_pinned(rows, max_tokens=max_tokens, count=count)


async def memory_refs(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[MemoryRef]:
    """Every memory item of the project, oldest first. 404 for another user's project."""
    await get_project(session, user_id, project_id)
    rows = await MemoryItemRepository(session, user_id).in_project(project_id)
    return [
        MemoryRef(
            id=r.id,
            kind=str(r.kind),
            status=str(r.status),
            priority=str(r.priority) if r.priority else None,
            title=r.title,
            body=r.body or "",
        )
        for r in rows
    ]
