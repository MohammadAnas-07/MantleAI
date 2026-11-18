"""Repositories for the conversations module. Every query filters by user_id."""

import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import desc, func, or_, select, update

from app.core.config import settings
from app.db.repository import UserScopedRepository
from app.modules.conversations.models import (
    ContextHandoff,
    Conversation,
    ConversationSummary,
    Message,
    MessageContext,
)
from app.modules.conversations.schemas import content_parts_adapter

_LOCK_COLUMNS = {"generating": "generating_since", "summary": "summary_started_at"}


class ConversationRepository(UserScopedRepository[Conversation]):
    model = Conversation

    async def claim_lock(self, conversation_id: uuid.UUID, lock: str) -> bool:
        """Atomically take the `generating` or `summary` lock. False if someone holds it.

        A lock older than CONVERSATION_LOCK_TIMEOUT_SECONDS is stale and is taken over.
        """
        column = getattr(Conversation, _LOCK_COLUMNS[lock])
        stale = func.now() - timedelta(seconds=settings.conversation_lock_timeout_seconds)
        stmt = (
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == self.user_id,
                or_(column.is_(None), column < stale),
            )
            .values({column: func.now()})
            .returning(Conversation.id)
            .execution_options(synchronize_session=False)
        )
        claimed = (await self.session.execute(stmt)).scalar_one_or_none() is not None
        await self._refresh(conversation_id)
        return claimed

    async def release_lock(self, conversation_id: uuid.UUID, lock: str) -> None:
        column = getattr(Conversation, _LOCK_COLUMNS[lock])
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id, Conversation.user_id == self.user_id)
            .values({column: None})
            .execution_options(synchronize_session=False)
        )
        await self.session.execute(stmt)
        await self._refresh(conversation_id)

    async def _refresh(self, conversation_id: uuid.UUID) -> None:
        obj = await self.session.get(Conversation, conversation_id)
        if obj is not None:
            await self.session.refresh(obj)


class MessageRepository(UserScopedRepository[Message]):
    model = Message

    async def add(self, **values: Any) -> Message:
        # Store content only in the provider-neutral part format.
        if "content" in values:
            parts = content_parts_adapter.validate_python(values["content"])
            values["content"] = content_parts_adapter.dump_python(parts, mode="json")
        return await super().add(**values)

    async def next_sequence(self, conversation_id: uuid.UUID) -> int:
        stmt = select(func.coalesce(func.max(Message.sequence), 0)).where(
            Message.user_id == self.user_id, Message.conversation_id == conversation_id
        )
        return int((await self.session.execute(stmt)).scalar_one()) + 1

    async def in_order(
        self,
        conversation_id: uuid.UUID,
        *,
        after_sequence: int = 0,
        limit: int | None = None,
    ) -> Sequence[Message]:
        """Messages of the conversation by sequence, those after `after_sequence` only."""
        stmt = (
            self._select()
            .where(Message.conversation_id == conversation_id, Message.sequence > after_sequence)
            .order_by(Message.sequence)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return (await self.session.execute(stmt)).scalars().all()


class ConversationSummaryRepository(UserScopedRepository[ConversationSummary]):
    model = ConversationSummary

    async def latest(self, conversation_id: uuid.UUID) -> ConversationSummary | None:
        """The current summary: the one covering the most messages (highest to_sequence).

        Ordered by sequence, not time: rows made in one transaction share the same now().
        """
        stmt = (
            self._select()
            .where(ConversationSummary.conversation_id == conversation_id)
            .order_by(desc(ConversationSummary.to_sequence), desc(ConversationSummary.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ContextHandoffRepository(UserScopedRepository[ContextHandoff]):
    model = ContextHandoff


class MessageContextRepository(UserScopedRepository[MessageContext]):
    model = MessageContext
