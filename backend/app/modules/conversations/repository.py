"""Repositories for the conversations module. Every query filters by user_id."""

import uuid
from typing import Any

from sqlalchemy import desc

from app.db.repository import UserScopedRepository
from app.modules.conversations.models import (
    ContextHandoff,
    Conversation,
    ConversationSummary,
    Message,
    MessageContext,
)
from app.modules.conversations.schemas import content_parts_adapter


class ConversationRepository(UserScopedRepository[Conversation]):
    model = Conversation


class MessageRepository(UserScopedRepository[Message]):
    model = Message

    async def add(self, **values: Any) -> Message:
        # Store content only in the provider-neutral part format.
        if "content" in values:
            parts = content_parts_adapter.validate_python(values["content"])
            values["content"] = content_parts_adapter.dump_python(parts, mode="json")
        return await super().add(**values)


class ConversationSummaryRepository(UserScopedRepository[ConversationSummary]):
    model = ConversationSummary

    async def latest(self, conversation_id: uuid.UUID) -> ConversationSummary | None:
        """The current summary: the newest row for the conversation."""
        stmt = (
            self._select()
            .where(ConversationSummary.conversation_id == conversation_id)
            .order_by(desc(ConversationSummary.created_at), desc(ConversationSummary.id))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ContextHandoffRepository(UserScopedRepository[ContextHandoff]):
    model = ContextHandoff


class MessageContextRepository(UserScopedRepository[MessageContext]):
    model = MessageContext
