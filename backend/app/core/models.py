"""Shared tables owned by `app/core`: User and AuditEvent."""

import uuid
from typing import Any

from sqlalchemy import String, false, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Entity, UserOwnedEntity

# v0.1 has exactly one user. The seed script creates it with this fixed id, and every
# request runs as this user until authentication exists.
DEFAULT_LOCAL_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class User(Entity):
    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String(200))
    is_local_default: Mapped[bool] = mapped_column(default=False, server_default=false())


class AuditEvent(UserOwnedEntity):
    """Security-relevant actions only. `details` must never hold secrets or file contents."""

    __tablename__ = "audit_events"

    event_type: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None]
    details: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )
