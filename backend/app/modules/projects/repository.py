"""Repositories for the projects module. Every query filters by user_id; memory queries also
filter by project_id."""

import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import func, select

from app.db.repository import UserScopedRepository
from app.modules.projects.models import (
    MemoryDependency,
    MemoryItem,
    MemoryItemKind,
    MemoryItemStatus,
    Project,
)


class ProjectRepository(UserScopedRepository[Project]):
    model = Project


class MemoryItemRepository(UserScopedRepository[MemoryItem]):
    model = MemoryItem

    async def page(
        self,
        project_id: uuid.UUID,
        *,
        kind: MemoryItemKind | None,
        status: MemoryItemStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[MemoryItem], int]:
        """One page in a stable order (created_at, then id) and the total count."""
        stmt = self._select().where(MemoryItem.project_id == project_id)
        if kind is not None:
            stmt = stmt.where(MemoryItem.kind == kind)
        if status is not None:
            stmt = stmt.where(MemoryItem.status == status)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.execute(
            stmt.order_by(MemoryItem.created_at, MemoryItem.id).limit(limit).offset(offset)
        )
        return rows.scalars().all(), int(total or 0)

    async def count(self, project_id: uuid.UUID, kind: MemoryItemKind) -> int:
        stmt = select(func.count()).where(
            MemoryItem.user_id == self.user_id,
            MemoryItem.project_id == project_id,
            MemoryItem.kind == kind,
        )
        return int(await self.session.scalar(stmt) or 0)

    async def in_project(
        self,
        project_id: uuid.UUID,
        *,
        ids: Collection[uuid.UUID] | None = None,
        kinds: Collection[MemoryItemKind] | None = None,
    ) -> Sequence[MemoryItem]:
        stmt = self._select().where(MemoryItem.project_id == project_id)
        if ids is not None:
            stmt = stmt.where(MemoryItem.id.in_(list(ids)))
        if kinds is not None:
            stmt = stmt.where(MemoryItem.kind.in_(list(kinds)))
        stmt = stmt.order_by(MemoryItem.created_at, MemoryItem.id)
        return (await self.session.execute(stmt)).scalars().all()

    async def superseded_by(
        self, project_id: uuid.UUID, newer_ids: Collection[uuid.UUID]
    ) -> Sequence[MemoryItem]:
        """Decisions that were replaced by any of `newer_ids`."""
        stmt = self._select().where(
            MemoryItem.project_id == project_id, MemoryItem.superseded_by_id.in_(list(newer_ids))
        )
        return (await self.session.execute(stmt)).scalars().all()


class MemoryDependencyRepository(UserScopedRepository[MemoryDependency]):
    model = MemoryDependency

    async def edges(self, project_id: uuid.UUID) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """All (task_id, depends_on_id) links of the project."""
        stmt = select(MemoryDependency.task_id, MemoryDependency.depends_on_id).where(
            MemoryDependency.user_id == self.user_id, MemoryDependency.project_id == project_id
        )
        return [(t, d) for t, d in (await self.session.execute(stmt)).all()]

    async def find(self, task_id: uuid.UUID, depends_on_id: uuid.UUID) -> MemoryDependency | None:
        rows = await self.list(task_id=task_id, depends_on_id=depends_on_id, limit=1)
        return rows[0] if rows else None
