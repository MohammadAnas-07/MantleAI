"""Generic async CRUD repositories. No business logic lives here.

`UserScopedRepository` is bound to one `user_id` when it is created, and every query it runs
filters by that id, so code using it can't read or change another user's rows.
Repositories flush but never commit; the caller owns the transaction.
"""

import uuid
from collections.abc import Sequence
from typing import Any, ClassVar

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Entity, UserOwnedEntity

# Columns callers may never set or change through a repository.
_PROTECTED = frozenset({"id", "user_id", "created_at", "updated_at"})


class Repository[ModelT: Entity]:
    """CRUD for one table that is not user data (for example the model catalog)."""

    model: ClassVar[type[Entity]]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _select(self) -> Select[tuple[ModelT]]:
        return select(self.model)  # type: ignore[return-value]

    def _scope_values(self) -> dict[str, Any]:
        return {}

    def _check_columns(self, values: dict[str, Any], *, allow_id: bool = False) -> None:
        columns = self.model.__table__.columns.keys()
        protected = _PROTECTED - ({"id"} if allow_id else set())
        for name in values:
            if name not in columns:
                raise ValueError(f"{self.model.__name__} has no column {name!r}")
            if name in protected:
                raise ValueError(f"{name!r} can't be set through a repository")

    def _where(self, stmt: Select[tuple[ModelT]], filters: dict[str, Any]) -> Select[Any]:
        self._check_columns(filters, allow_id=True)
        for name, value in filters.items():
            stmt = stmt.where(getattr(self.model, name) == value)
        return stmt

    async def add(self, **values: Any) -> ModelT:
        self._check_columns(values)
        obj = self.model(**values, **self._scope_values())
        self.session.add(obj)
        await self.session.flush()
        return obj  # type: ignore[return-value]

    async def get(self, id: uuid.UUID) -> ModelT | None:
        result = await self.session.execute(self._select().where(self.model.id == id))
        return result.scalar_one_or_none()

    async def list(self, *, limit: int = 100, offset: int = 0, **filters: Any) -> Sequence[ModelT]:
        stmt = self._where(self._select(), filters)
        stmt = stmt.order_by(self.model.created_at, self.model.id).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update(self, id: uuid.UUID, **values: Any) -> ModelT | None:
        self._check_columns(values)
        obj = await self.get(id)
        if obj is None:
            return None
        for name, value in values.items():
            setattr(obj, name, value)
        await self.session.flush()
        return obj

    async def delete(self, id: uuid.UUID) -> bool:
        """Delete one row. Dependent rows go with it through the database's ON DELETE rules."""
        obj = await self.get(id)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True


class UserScopedRepository[ModelT: UserOwnedEntity](Repository[ModelT]):
    """CRUD for one user-data table. Every query filters by the bound `user_id`."""

    model: ClassVar[type[UserOwnedEntity]]

    def __init__(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        super().__init__(session)
        self.user_id = user_id

    def _select(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.user_id == self.user_id)  # type: ignore[return-value]

    def _scope_values(self) -> dict[str, Any]:
        return {"user_id": self.user_id}
