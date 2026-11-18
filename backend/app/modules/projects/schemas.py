"""Request and response bodies for project memory.

Text rules: surrounding whitespace is trimmed, Windows line endings become "\\n", any Unicode is
fine (Hindi, emoji), control characters and null bytes are rejected, titles are one line. Lengths
come from settings so they can change without a code change.
"""

import unicodedata
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings

Kind = Literal["requirement", "decision", "task"]

_ALLOWED_CONTROL = {"\n", "\t"}


def clean_text(value: str, *, max_length: int, one_line: bool = False) -> str:
    """Trim and validate user text. Raises ValueError with a message for the 422 response."""
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("must not be empty or only whitespace")
    bad = [c for c in text if unicodedata.category(c) == "Cc" and c not in _ALLOWED_CONTROL]
    if bad:
        raise ValueError(f"must not contain control characters (found U+{ord(bad[0]):04X})")
    if one_line and ("\n" in text or "\t" in text):
        raise ValueError("must be a single line")
    if len(text) > max_length:
        raise ValueError(f"must be at most {max_length} characters (got {len(text)})")
    return text


def _title(value: str) -> str:
    return clean_text(value, max_length=settings.memory_title_max_length, one_line=True)


def _text(value: str | None) -> str | None:
    # None means "no value" (and clears the field in a PATCH); an empty string is an error.
    if value is None:
        return None
    return clean_text(value, max_length=settings.memory_text_max_length)


def _past(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if value > datetime.now(UTC):
        raise ValueError("must not be in the future")
    return value


class _MemoryFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str | None = None
    status: str | None = None
    priority: str | None = None
    why: str | None = None
    alternatives: str | None = None
    decided_at: datetime | None = None

    @field_validator("body", "why", "alternatives")
    @classmethod
    def _check_text(cls, value: str | None) -> str | None:
        return _text(value)

    @field_validator("decided_at")
    @classmethod
    def _check_date(cls, value: datetime | None) -> datetime | None:
        return _past(value)


class MemoryItemCreate(_MemoryFields):
    """For a decision, `body` is what was decided."""

    kind: Kind
    title: str

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str) -> str:
        return _title(value)


class MemoryItemPatch(_MemoryFields):
    """Only the fields that are sent change. Sending none is an error."""

    title: str | None = None

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("can't be null")
        return _title(value)

    @model_validator(mode="after")
    def _not_empty(self) -> "MemoryItemPatch":
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        return self

    def changes(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.model_fields_set}


class NewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    body: str | None = None
    why: str | None = None
    alternatives: str | None = None
    decided_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def _check_title(cls, value: str) -> str:
        return _title(value)

    @field_validator("body", "why", "alternatives")
    @classmethod
    def _check_text(cls, value: str | None) -> str | None:
        return _text(value)

    @field_validator("decided_at")
    @classmethod
    def _check_date(cls, value: datetime | None) -> datetime | None:
        return _past(value)


class SupersedeIn(BaseModel):
    """Replace a decision: either with a new one (`decision`) or with an existing one (`by_id`)."""

    model_config = ConfigDict(extra="forbid")

    decision: NewDecision | None = None
    by_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_way(self) -> "SupersedeIn":
        if (self.decision is None) == (self.by_id is None):
            raise ValueError("send exactly one of 'decision' or 'by_id'")
        return self


class DependencyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depends_on_id: uuid.UUID


class MemoryItemOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    title: str
    body: str
    status: str
    priority: str | None
    why: str | None
    alternatives: str | None
    decided_at: datetime | None
    superseded_by_id: uuid.UUID | None
    supersedes_ids: list[uuid.UUID] = Field(default_factory=list)
    depends_on_ids: list[uuid.UUID] = Field(default_factory=list)
    is_blocked: bool | None = None  # tasks only: a dependency is not done
    source: str
    created_at: datetime
    updated_at: datetime


class MemoryPage(BaseModel):
    items: list[MemoryItemOut]
    total: int
    limit: int
    offset: int
