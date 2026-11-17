"""Declarative base, naming convention and column helpers shared by every model.

Every table gets a UUID `id` (server default `gen_random_uuid()`), and timezone-aware
`created_at` / `updated_at`. User-data tables also get an indexed `user_id`.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, MetaData, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Constraint and index names follow one pattern, so migrations are predictable.
# Foreign keys are named after the table and column only, to stay under PostgreSQL's
# 63-character identifier limit.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_N_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        uuid.UUID: PG_UUID(as_uuid=True),
        dict[str, Any]: JSONB,
        list[dict[str, Any]]: JSONB,
        list[str]: JSONB,
    }


class Entity(Base):
    """Abstract base: `id`, `created_at` and `updated_at` on every table."""

    __abstract__ = True
    # Read server-generated values (id, timestamps) back with RETURNING, so async code
    # never triggers a lazy load to get them.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class UserOwnedEntity(Entity):
    """Abstract base for user-data tables: adds a non-null, indexed `user_id`.

    Deleting a user deletes all of their rows.
    """

    __abstract__ = True

    @declared_attr
    def user_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


def str_enum(enum_cls: type[StrEnum]) -> Enum:
    """Store a Python enum as a plain VARCHAR (no PostgreSQL enum type, no CHECK constraint).

    Adding a value then needs no migration. Values are validated in Python.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=False,
        length=32,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


def fk(target: str, *, ondelete: str | None = None) -> ForeignKey:
    """Foreign key to `<table>.id`. `ondelete=None` means NO ACTION (block the delete).

    SET NULL keys are DEFERRABLE INITIALLY DEFERRED. One delete can cascade through several
    tables; a row whose link is set to NULL may still point at another row that the same
    cascade is deleting, and an immediate check would fail before the cascade finishes.
    """
    if ondelete == "SET NULL":
        return ForeignKey(f"{target}.id", ondelete=ondelete, deferrable=True, initially="DEFERRED")
    return ForeignKey(f"{target}.id", ondelete=ondelete)
