"""Repositories for the rag module. Every query filters by user_id."""

import uuid

from app.db.repository import UserScopedRepository
from app.modules.rag.models import Chunk, Document, IndexRun, ProjectProfile


class IndexRunRepository(UserScopedRepository[IndexRun]):
    model = IndexRun


class DocumentRepository(UserScopedRepository[Document]):
    model = Document

    async def get_by_path(self, project_id: uuid.UUID, path: str) -> Document | None:
        rows = await self.list(project_id=project_id, path=path, limit=1)
        return rows[0] if rows else None


class ChunkRepository(UserScopedRepository[Chunk]):
    model = Chunk


class ProjectProfileRepository(UserScopedRepository[ProjectProfile]):
    model = ProjectProfile

    async def get_for_project(self, project_id: uuid.UUID) -> ProjectProfile | None:
        rows = await self.list(project_id=project_id, limit=1)
        return rows[0] if rows else None
