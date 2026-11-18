"""Tables owned by the conversations module."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UserOwnedEntity, fk, str_enum


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MessageStatus(StrEnum):
    COMPLETE = "complete"
    STREAMING = "streaming"
    ERROR = "error"
    CANCELLED = "cancelled"


class SummaryBuiltAt(StrEnum):
    BACKGROUND = "background"
    SWITCH = "switch"


class HandoffReason(StrEnum):
    USER_CHOICE = "user_choice"
    RATE_LIMIT = "rate_limit"
    CONTEXT_LIMIT = "context_limit"
    PROVIDER_ERROR = "provider_error"


class ContextSourceType(StrEnum):
    CHUNK = "chunk"
    MEMORY_ITEM = "memory_item"
    SUMMARY = "summary"


class Conversation(UserOwnedEntity):
    __tablename__ = "conversations"

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="", server_default="")
    current_model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)
    # Locks, claimed with an atomic UPDATE. Set = a job is running since then. A lock older than
    # CONVERSATION_LOCK_TIMEOUT_SECONDS is stale (crashed job) and can be claimed again.
    generating_since: Mapped[datetime | None]  # one reply at a time (else 409)
    summary_started_at: Mapped[datetime | None]  # one rolling-summary job at a time
    # Error code of the last failed rolling-summary job (rule 55); cleared on success.
    summary_error: Mapped[str | None] = mapped_column(String(64))


class Message(UserOwnedEntity):
    """One message in a provider-neutral format.

    `content` is a JSON list of parts, validated by `schemas.ContentPart`:
    `{"type": "text", "text": ...}`, `{"type": "tool_call", "id", "name", "arguments"}` and
    `{"type": "tool_result", "tool_call_id", "content", "is_error"}`.
    """

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
        UniqueConstraint("conversation_id", "sequence"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        fk("conversations", ondelete="CASCADE"), index=True
    )
    # 1, 2, 3, ... per conversation: the order of the conversation, independent of timestamps.
    sequence: Mapped[int]
    role: Mapped[MessageRole] = mapped_column(str_enum(MessageRole))
    content: Mapped[list[dict[str, Any]]] = mapped_column(default=list, server_default="[]")
    # The model that produced this message; null for user messages.
    model_id: Mapped[uuid.UUID | None] = mapped_column(fk("model_configs"), index=True)
    status: Mapped[MessageStatus] = mapped_column(
        str_enum(MessageStatus), default=MessageStatus.COMPLETE
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    # Tokens of this message's own content, used to fit history into a context window.
    token_count: Mapped[int] = mapped_column(default=0, server_default="0")
    # Provider-reported usage for the call that produced this message (assistant only).
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]


class ConversationSummary(UserOwnedEntity):
    """Rolling summary. A new row per update; the current one covers the highest `to_sequence`.

    It covers messages `from_sequence`..`to_sequence`, and is incremental: each new row is the
    previous summary plus the messages after its `to_sequence`.
    """

    __tablename__ = "conversation_summaries"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        fk("conversations", ondelete="CASCADE"), index=True
    )
    from_sequence: Mapped[int]
    to_sequence: Mapped[int]
    summary: Mapped[str] = mapped_column(Text)
    up_to_message_id: Mapped[uuid.UUID] = mapped_column(
        fk("messages", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)
    built_at: Mapped[SummaryBuiltAt] = mapped_column(str_enum(SummaryBuiltAt))
    token_count: Mapped[int] = mapped_column(default=0, server_default="0")


class ContextHandoff(UserOwnedEntity):
    """One row per model switch."""

    __tablename__ = "context_handoffs"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        fk("conversations", ondelete="CASCADE"), index=True
    )
    from_model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)
    to_model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)
    reason: Mapped[HandoffReason] = mapped_column(str_enum(HandoffReason))
    conversation_summary_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("conversation_summaries", ondelete="SET NULL"), index=True
    )
    # The oldest message carried over verbatim; null when no message is carried (empty history).
    first_raw_message_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("messages", ondelete="SET NULL"), index=True
    )
    tokens_before: Mapped[int] = mapped_column(default=0, server_default="0")
    tokens_after: Mapped[int] = mapped_column(default=0, server_default="0")
    # The handoff note shown to the user, built without an LLM and never sent to a model:
    # messages carried verbatim, summary range and size, pinned items, what was dropped.
    note: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=text("'{}'::jsonb"))


class MessageContext(UserOwnedEntity):
    """What was used to answer one message. `source_id` points at a Chunk, MemoryItem or
    ConversationSummary, depending on `source_type`, so it has no foreign key."""

    __tablename__ = "message_contexts"

    message_id: Mapped[uuid.UUID] = mapped_column(fk("messages", ondelete="CASCADE"), index=True)
    source_type: Mapped[ContextSourceType] = mapped_column(str_enum(ContextSourceType))
    source_id: Mapped[uuid.UUID]
    score: Mapped[float | None]
    rank: Mapped[int]
