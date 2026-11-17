"""Provider-neutral message content parts, stored as JSON in `messages.content`."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


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
