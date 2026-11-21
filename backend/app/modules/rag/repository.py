"""Repositories for the rag module. Every query filters by user_id."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.dialects.postgresql import insert

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


FACT_LISTS = (
    "dependencies", "markers", "manifests", "frameworks", "commands", "layout", "entry_points"
)  # fmt: skip


class ProjectProfileRepository(UserScopedRepository[ProjectProfile]):
    model = ProjectProfile

    async def get_for_project(self, project_id: uuid.UUID) -> ProjectProfile | None:
        # populate_existing: `save` writes with a Core upsert, which a loaded row doesn't see.
        return await self.session.scalar(
            self._select()
            .where(ProjectProfile.project_id == project_id)
            .execution_options(populate_existing=True)
        )

    async def save(
        self,
        project_id: uuid.UUID,
        index_run_id: uuid.UUID,
        facts: dict[str, Any],
        built_at: datetime,
    ) -> None:
        """Replace the project's facts in one statement. A fact field missing from `facts` is
        reset to empty, so nothing from an older build survives. The upsert on the unique
        project_id means two builds at once still leave one row."""
        values: dict[str, Any] = {name: facts.get(name, []) for name in FACT_LISTS}
        values["languages"] = facts.get("languages", {})
        values |= {"index_run_id": index_run_id, "built_at": built_at}
        statement = insert(ProjectProfile).values(
            user_id=self.user_id, project_id=project_id, **values
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[ProjectProfile.project_id],
                set_=values,
                where=ProjectProfile.user_id == self.user_id,
            )
        )
