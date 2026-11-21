"""Request and response bodies of the rag endpoints."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings


class SourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_path: str = Field(min_length=1, max_length=4096)


class IndexStartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Index even when the estimate is above INDEX_COST_LIMIT_USD.
    force: bool = False


class EmptyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IndexStatusOut(BaseModel):
    project_id: uuid.UUID
    root_path: str | None
    indexed: bool
    last_indexed_at: datetime | None
    needs_reindex: bool
    reindex_reasons: list[str]
    embedding_models: list[str]
    files: int
    active_run_id: uuid.UUID | None


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: str  # queued | running | succeeded | failed | cancelled
    error: str | None
    files_seen: int
    files_indexed: int
    files_skipped: int
    files_unchanged: int
    chunks_created: int
    tokens: int
    cost_estimate_usd: Decimal | None
    force: bool
    embedding_model: str | None
    root_path: str | None
    estimate: dict[str, Any]
    skip_report: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested_at: datetime | None


class RunStarted(BaseModel):
    run_id: uuid.UUID
    status: str
    estimate: dict[str, Any]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    path: str
    status: str  # pending | indexed | skipped
    skip_reason: str | None
    language: str | None
    size_bytes: int
    line_count: int
    parse_fallback: str | None
    embedding_model: str | None
    updated_at: datetime


class DocumentPageOut(BaseModel):
    items: list[DocumentOut]
    total: int
    limit: int
    offset: int
    counts: dict[str, int]


class LanguageShareOut(BaseModel):
    name: str
    files: int
    share: float = Field(description="Share of the counted files, 0 to 1.")


class SourcedNameOut(BaseModel):
    name: str
    source: str = Field(description="The file this fact was read from.")


class DependencyOut(BaseModel):
    name: str
    ecosystem: str  # python | node
    dev: bool
    source: str


class CommandOut(BaseModel):
    name: str
    command: str
    source: str
    kind: str  # script | make | inferred


class ManifestOut(BaseModel):
    kind: str  # pyproject | requirements | package_json | makefile | lock_file
    source: str


class EntryPointOut(BaseModel):
    source: str
    kind: str  # the file's language


class LayoutOut(BaseModel):
    path: str
    files: int


class ProjectProfileOut(BaseModel):
    """Facts read from the project's files by the last successful index run, without a model.
    All text comes from the repository: show it as plain text."""

    project_id: uuid.UUID
    built: bool
    built_at: datetime | None
    index_run_id: uuid.UUID | None
    out_of_date: bool
    out_of_date_reasons: list[str] = Field(description="source_changed | index_changed")
    languages: list[LanguageShareOut]
    frameworks: list[SourcedNameOut]
    commands: list[CommandOut]
    markers: list[SourcedNameOut]
    manifests: list[ManifestOut]
    dependencies: list[DependencyOut]
    entry_points: list[EntryPointOut]
    layout: list[LayoutOut]


class SearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(max_length=100_000)  # the real limit is checked with a clear message
    top_k: int | None = Field(default=None, ge=1)
    mode: Literal["hybrid", "vector", "text"] = "hybrid"
    path_prefix: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, max_length=50)

    @field_validator("top_k")
    @classmethod
    def _cap(cls, value: int | None) -> int | None:
        if value is not None and value > settings.retrieval_max_top_k:
            raise ValueError(f"must be at most {settings.retrieval_max_top_k}")
        return value


class SearchHitOut(BaseModel):
    path: str
    start_line: int
    end_line: int
    language: str | None
    symbol: str | None
    vector_rank: int | None
    text_rank: int | None
    score: float
    chunk_ids: list[uuid.UUID]
    text: str


class SearchOut(BaseModel):
    results: list[SearchHitOut]
    needs_reindex: bool
    reindex_reasons: list[str]
