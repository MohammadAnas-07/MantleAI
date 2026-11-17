"""Repositories for the projects module. Every query filters by user_id."""

from app.db.repository import UserScopedRepository
from app.modules.projects.models import MemoryItem, Project


class ProjectRepository(UserScopedRepository[Project]):
    model = Project


class MemoryItemRepository(UserScopedRepository[MemoryItem]):
    model = MemoryItem
