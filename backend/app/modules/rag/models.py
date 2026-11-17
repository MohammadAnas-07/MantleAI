"""Tables owned by the rag module."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import UserOwnedEntity, fk, str_enum


class IndexRunStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IndexRun(UserOwnedEntity):
    __tablename__ = "index_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    status: Mapped[IndexRunStatus] = mapped_column(
        str_enum(IndexRunStatus), default=IndexRunStatus.RUNNING
    )
    files_seen: Mapped[int] = mapped_column(default=0, server_default="0")
    files_indexed: Mapped[int] = mapped_column(default=0, server_default="0")
    files_skipped: Mapped[int] = mapped_column(default=0, server_default="0")
    chunks_created: Mapped[int] = mapped_column(default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None]
    embedding_model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)


class Document(UserOwnedEntity):
    """One indexed file."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("project_id", "path"),)

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)  # relative to the project's root_path
    content_hash: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    language: Mapped[str | None] = mapped_column(String(50))
    last_index_run_id: Mapped[uuid.UUID] = mapped_column(fk("index_runs"), index=True)


class Chunk(UserOwnedEntity):
    """A piece of a document with its embedding.

    The `embedding` column has ONE fixed dimension, `settings.embedding_dimensions`
    (EMBEDDING_DIMENSIONS, default 1536). Changing it needs a new Alembic migration that
    alters the column and rebuilds the HNSW index, and every project must be re-indexed.
    Retrieval only compares chunks whose `embedding_model` matches the query's model.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(fk("documents", ondelete="CASCADE"), index=True)
    # Copied from the document for fast filtering in retrieval.
    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    start_line: Mapped[int]
    end_line: Mapped[int]
    token_count: Mapped[int] = mapped_column(default=0, server_default="0")
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimensions))
    embedding_model: Mapped[str] = mapped_column(String(200))
    embedding_dimensions: Mapped[int]


class ProjectProfile(UserOwnedEntity):
    """Facts about a project, built without an LLM at the end of each index run."""

    __tablename__ = "project_profiles"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    languages: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )
    dependencies: Mapped[list[str]] = mapped_column(default=list, server_default="[]")
    markers: Mapped[list[str]] = mapped_column(default=list, server_default="[]")
    index_run_id: Mapped[uuid.UUID] = mapped_column(fk("index_runs"), index=True)
