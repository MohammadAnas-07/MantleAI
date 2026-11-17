"""Tables owned by the teaching module."""

import uuid
from enum import StrEnum

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UserOwnedEntity, fk, str_enum


class ConceptSuggestionStatus(StrEnum):
    NEW = "new"
    DISMISSED = "dismissed"
    NOTED = "noted"


class TeachingNote(UserOwnedEntity):
    """Created only when the user asks (D5)."""

    __tablename__ = "teaching_notes"

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    concept: Mapped[str] = mapped_column(String(200))
    what: Mapped[str] = mapped_column(Text)
    why_here: Mapped[str] = mapped_column(Text)
    how: Mapped[str] = mapped_column(Text)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("messages", ondelete="SET NULL"), index=True
    )
    stage_key: Mapped[str | None] = mapped_column(String(50))
    model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)


class ConceptSuggestion(UserOwnedEntity):
    """The passive "concepts for this project" list, built by rules only, no LLM (D10)."""

    __tablename__ = "concept_suggestions"
    __table_args__ = (UniqueConstraint("project_id", "rule_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(String(100))
    concept: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[ConceptSuggestionStatus] = mapped_column(
        str_enum(ConceptSuggestionStatus), default=ConceptSuggestionStatus.NEW
    )
    teaching_note_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("teaching_notes", ondelete="SET NULL"), index=True
    )
