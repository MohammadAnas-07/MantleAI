"""Repositories for the teaching module. Every query filters by user_id."""

from app.db.repository import UserScopedRepository
from app.modules.teaching.models import ConceptSuggestion, TeachingNote


class TeachingNoteRepository(UserScopedRepository[TeachingNote]):
    model = TeachingNote


class ConceptSuggestionRepository(UserScopedRepository[ConceptSuggestion]):
    model = ConceptSuggestion
