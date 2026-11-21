"""Tables owned by the rag module."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import UserOwnedEntity, fk, str_enum


class IndexRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_RUN_STATUSES = (IndexRunStatus.QUEUED, IndexRunStatus.RUNNING)


class IndexRun(UserOwnedEntity):
    """One indexing job. At most one queued or running job per project (partial unique index)."""

    __tablename__ = "index_runs"
    __table_args__ = (
        Index(
            "uq_index_runs_project_id_active",
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    status: Mapped[IndexRunStatus] = mapped_column(
        str_enum(IndexRunStatus), default=IndexRunStatus.QUEUED
    )
    files_seen: Mapped[int] = mapped_column(default=0, server_default="0")
    files_indexed: Mapped[int] = mapped_column(default=0, server_default="0")
    files_skipped: Mapped[int] = mapped_column(default=0, server_default="0")
    files_unchanged: Mapped[int] = mapped_column(default=0, server_default="0")
    chunks_created: Mapped[int] = mapped_column(default=0, server_default="0")
    tokens: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    cost_estimate_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    cancel_requested_at: Mapped[datetime | None]
    force: Mapped[bool] = mapped_column(default=False, server_default=false())
    embedding_model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)
    # Snapshots, so a later settings change can't alter what this run did.
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    root_path: Mapped[str | None] = mapped_column(Text)
    # The estimate checked before the run, and skip counts per reason with example paths.
    estimate: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )
    skip_report: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )


class DocumentStatus(StrEnum):
    PENDING = "pending"  # its segments are being embedded
    INDEXED = "indexed"
    SKIPPED = "skipped"


class Document(UserOwnedEntity):
    """One file of the project: indexed, being indexed, or skipped with a reason.

    `content_hash` is set only once every segment of that content is stored, so a run that
    stops halfway leaves the old hash (or none) and the next run picks the file up again.
    """

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("project_id", "path"),)

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)  # relative to the project's root_path, POSIX form
    status: Mapped[DocumentStatus] = mapped_column(
        str_enum(DocumentStatus), default=DocumentStatus.INDEXED
    )
    skip_reason: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str | None] = mapped_column(String(64))  # sha256 of the LF text
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mtime_ns: Mapped[int | None] = mapped_column(BigInteger)
    line_count: Mapped[int] = mapped_column(default=0, server_default="0")
    language: Mapped[str | None] = mapped_column(String(50))
    # "syntax_error" or "no_grammar" when code was split by lines instead.
    parse_fallback: Mapped[str | None] = mapped_column(String(32))
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    # secret_scan.RULES_VERSION the content was last checked with. A file checked with older
    # rules is read and checked again even when its size and mtime didn't change.
    scan_version: Mapped[int | None] = mapped_column(SmallInteger)
    last_index_run_id: Mapped[uuid.UUID] = mapped_column(fk("index_runs"), index=True)


class Chunk(UserOwnedEntity):
    """A segment of a document with its embedding.

    The `embedding` column has ONE fixed dimension, `settings.embedding_dimensions`
    (EMBEDDING_DIMENSIONS, default 1536). Changing it needs a new Alembic migration that
    alters the column and rebuilds the HNSW index, and every project must be re-indexed.
    Retrieval only compares chunks whose `embedding_model` matches the query's model.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_project_id_embedding_model", "project_id", "embedding_model"),
        Index("ix_chunks_search_tsv", "search_tsv", postgresql_using="gin"),
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
    language: Mapped[str | None] = mapped_column(String(50))
    chunk_type: Mapped[str] = mapped_column(String(32), default="lines", server_default="lines")
    symbol: Mapped[str | None] = mapped_column(Text)
    # sha256 of the text sent to the embedder (path + symbol + content): the same hash and
    # model means the stored vector can be reused.
    content_hash: Mapped[str] = mapped_column(String(64), default="", server_default="")
    # Identifiers split into words, for full-text search; `search_tsv` is computed from it.
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    search_tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', search_text)", persisted=True)
    )


class ProjectProfile(UserOwnedEntity):
    """Facts about a project, built without an LLM at the end of each successful index run
    (rag/profile.py). One row per project, replaced on every build. Every list item is an
    object with a `source` path, the file the fact was read from."""

    __tablename__ = "project_profiles"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    # {"python": 42, "typescript": 10}: indexed files per language.
    languages: Mapped[dict[str, Any]] = mapped_column(
        default=dict, server_default=text("'{}'::jsonb")
    )
    # [{"name", "ecosystem", "dev", "source"}]
    dependencies: Mapped[list[dict[str, Any]]] = mapped_column(default=list, server_default="[]")
    # [{"name", "source"}]: dockerfile, compose, migrations, ci_workflows, tests
    markers: Mapped[list[dict[str, Any]]] = mapped_column(default=list, server_default="[]")
    # [{"kind", "source"}]: pyproject, requirements, package_json, lock files, ...
    manifests: Mapped[list[dict[str, Any]]] = mapped_column(default=list, server_default="[]")
    # [{"name", "source"}]: hints from dependency names
    frameworks: Mapped[list[dict[str, Any]]] = mapped_column(default=list, server_default="[]")
    # [{"name", "command", "source"}]: package.json scripts, pyproject scripts
    commands: Mapped[list[dict[str, Any]]] = mapped_column(default=list, server_default="[]")
    # [{"path", "files"}]: top folders, two levels at most
    layout: Mapped[list[dict[str, Any]]] = mapped_column(default=list, server_default="[]")
    # [{"source", "kind"}]: main.py, manage.py, src/main.tsx, ...
    entry_points: Mapped[list[dict[str, Any]]] = mapped_column(default=list, server_default="[]")
    built_at: Mapped[datetime | None]
    index_run_id: Mapped[uuid.UUID] = mapped_column(fk("index_runs"), index=True)
