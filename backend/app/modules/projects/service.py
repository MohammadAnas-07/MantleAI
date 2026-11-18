"""Public interface of the projects module (rule 6).

v0.1 so far: read a project, and read its pinned memory items for the context builder. Memory
CRUD comes in `feat/project-memory`.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.modules.projects.models import MemoryItemKind, MemoryItemStatus
from app.modules.projects.repository import MemoryItemRepository, ProjectRepository


@dataclass(frozen=True)
class ProjectInfo:
    id: uuid.UUID
    name: str
    description: str | None


@dataclass(frozen=True)
class PinnedItem:
    kind: str  # requirement | decision | task
    title: str
    body: str


# Pinned items, most important first. When the token budget is tight, the context builder drops
# from the end of this list.
_PINNED_ORDER = [MemoryItemKind.DECISION, MemoryItemKind.REQUIREMENT, MemoryItemKind.TASK]


async def get_project(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> ProjectInfo:
    project = await ProjectRepository(session, user_id).get(project_id)
    if project is None:
        raise NotFound("Project not found.")
    return ProjectInfo(project.id, project.name, project.description)


async def create_project(
    session: AsyncSession, user_id: uuid.UUID, name: str, description: str | None
) -> ProjectInfo:
    project = await ProjectRepository(session, user_id).add(name=name, description=description)
    return ProjectInfo(project.id, project.name, project.description)


async def list_projects(session: AsyncSession, user_id: uuid.UUID) -> list[ProjectInfo]:
    rows = await ProjectRepository(session, user_id).list(archived_at=None, limit=500)
    return [ProjectInfo(p.id, p.name, p.description) for p in rows]


async def list_pinned_items(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[PinnedItem]:
    """Active decisions and requirements, and open tasks. Read-only."""
    rows = await MemoryItemRepository(session, user_id).list(
        project_id=project_id, status=MemoryItemStatus.ACTIVE, limit=500
    )
    rank = {kind: i for i, kind in enumerate(_PINNED_ORDER)}
    rows = sorted(rows, key=lambda r: rank[r.kind])
    return [PinnedItem(kind=r.kind.value, title=r.title, body=r.body) for r in rows]
