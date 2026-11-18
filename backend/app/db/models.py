"""Imports every model so `Base.metadata` knows all tables (used by Alembic and tests).

This file is database plumbing, not a module, so it may import each module's models.
Application code must not import models from here; use the owning module instead.
"""

from app.core.models import AuditEvent, User
from app.db.base import Base
from app.modules.conversations.models import (
    ContextHandoff,
    Conversation,
    ConversationSummary,
    Message,
    MessageContext,
)
from app.modules.llm.models import ModelConfig, ProviderCredential, UsageRecord, UserModelSettings
from app.modules.projects.models import MemoryDependency, MemoryItem, Project
from app.modules.rag.models import Chunk, Document, IndexRun, ProjectProfile
from app.modules.teaching.models import ConceptSuggestion, TeachingNote
from app.modules.workflow.models import AgentRun, StageState, WorkflowRun

__all__ = [
    "AgentRun",
    "AuditEvent",
    "Base",
    "Chunk",
    "ConceptSuggestion",
    "ContextHandoff",
    "Conversation",
    "ConversationSummary",
    "Document",
    "IndexRun",
    "MemoryDependency",
    "MemoryItem",
    "Message",
    "MessageContext",
    "ModelConfig",
    "Project",
    "ProjectProfile",
    "ProviderCredential",
    "StageState",
    "TeachingNote",
    "UsageRecord",
    "User",
    "UserModelSettings",
    "WorkflowRun",
]
