"""Provider-neutral message content parts (stored as JSON in `messages.content`), and the
request/response bodies of the conversation endpoints."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ToolCallPart(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultPart(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    content: str
    is_error: bool = False


ContentPart = Annotated[TextPart | ToolCallPart | ToolResultPart, Field(discriminator="type")]

content_parts_adapter: TypeAdapter[list[ContentPart]] = TypeAdapter(list[ContentPart])


# ---- API bodies ------------------------------------------------------------------------------


class ConversationCreate(BaseModel):
    model_id: uuid.UUID
    title: str = Field(default="", max_length=300)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    current_model_id: uuid.UUID
    generating: bool
    summary_error: str | None
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=200_000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence: int
    role: str
    content: list[dict[str, Any]]
    model_id: uuid.UUID | None
    status: str  # complete | streaming | error | cancelled (cancelled = incomplete)
    error_code: str | None
    token_count: int
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime


class SummaryOut(BaseModel):
    summary: str | None
    from_sequence: int | None
    to_sequence: int | None
    model_id: uuid.UUID | None
    built_at: str | None
    token_count: int
    running: bool
    last_error: str | None


class SwitchModelIn(BaseModel):
    model_id: uuid.UUID
    reason: Literal["user_choice", "rate_limit", "context_limit", "provider_error"] = "user_choice"


class HandoffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_model_id: uuid.UUID
    to_model_id: uuid.UUID
    reason: str
    conversation_summary_id: uuid.UUID | None
    first_raw_message_id: uuid.UUID | None
    tokens_before: int
    tokens_after: int
    note: dict[str, Any]
    created_at: datetime


class SwitchOut(BaseModel):
    conversation: ConversationOut
    handoff: HandoffOut
    preview: dict[str, Any]
