"""Repositories for the shared tables: User and AuditEvent."""

from app.core.models import AuditEvent, User
from app.db.repository import Repository, UserScopedRepository


class UserRepository(Repository[User]):
    """Users are not user data (they are the owners), so this repository is not scoped."""

    model = User

    async def get_default(self) -> User | None:
        rows = await self.list(is_local_default=True, limit=1)
        return rows[0] if rows else None


class AuditEventRepository(UserScopedRepository[AuditEvent]):
    model = AuditEvent
