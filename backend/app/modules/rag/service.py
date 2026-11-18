"""Public interface of the rag module (rule 6): the project's source folder, indexing,
the index status, search, and retrieval for the context builder.

rag may call llm (embeddings) and projects (the project and its folder); see ADR 0006.
The only model calls are embeddings, made through the gateway with purpose "embedding".
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, NotFound
from app.modules.llm.service import (
    Gateway,
    ModelUnavailable,
    UsageLinks,
    UsageTrigger,
    get_embedding_model,
)
from app.modules.projects.service import ProjectInfo, get_project, set_root_path
from app.modules.rag.indexer import (
    CostLimitExceeded,
    Estimate,
    IndexInProgress,
    NoSourcePath,
    active_run,
    estimate_index,
    recover_interrupted_runs,
    request_cancel,
    run_index_job,
    start_index,
)
from app.modules.rag.models import (
    Chunk,
    Document,
    DocumentStatus,
    IndexRun,
    IndexRunStatus,
)
from app.modules.rag.search import Block, Hit, SearchMode, hybrid_search, merge_adjacent
from app.modules.rag.source import InvalidSourcePath, validate_source_path

__all__ = [
    "CostLimitExceeded",
    "Estimate",
    "IndexInProgress",
    "IndexStatus",
    "InvalidQuery",
    "InvalidSourcePath",
    "NoSourcePath",
    "NotIndexed",
    "RetrievalOutcome",
    "RetrievedBlock",
    "blocks_for_chunks",
    "cancel_run",
    "delete_index",
    "estimate_index",
    "get_run",
    "index_status",
    "index_status_many",
    "list_documents",
    "list_runs",
    "recover_interrupted_runs",
    "retrieve_for_context",
    "run_index_job",
    "search",
    "set_source",
    "start_index",
]


class InvalidQuery(AppError):
    status_code = 422
    code = "invalid_query"


class NotIndexed(AppError):
    status_code = 409
    code = "not_indexed"


@dataclass(frozen=True)
class RetrievedBlock:
    """Code retrieved for a prompt: one file range, with how it ranked."""

    path: str
    start_line: int
    end_line: int
    language: str | None
    symbol: str | None
    text: str
    score: float  # fused RRF score
    vector_rank: int | None
    text_rank: int | None
    chunk_ids: tuple[uuid.UUID, ...]


def _block(b: Block) -> RetrievedBlock:
    return RetrievedBlock(b.path, b.start_line, b.end_line, b.language, b.symbol, b.text,
                          b.score, b.vector_rank, b.text_rank, tuple(b.chunk_ids))  # fmt: skip


# ---- status ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class IndexStatus:
    project_id: uuid.UUID
    root_path: str | None
    indexed: bool  # a run succeeded and files are stored
    last_indexed_at: datetime | None
    needs_reindex: bool
    # "embedding_model_changed" | "source_changed"
    reindex_reasons: tuple[str, ...] = ()
    embedding_models: tuple[str, ...] = ()
    files: int = 0
    active_run_id: uuid.UUID | None = None


async def index_status_many(
    session: AsyncSession, user_id: uuid.UUID, projects: Sequence[ProjectInfo]
) -> dict[uuid.UUID, IndexStatus]:
    """The index status of many projects with a fixed number of queries, whatever their count."""
    ids = [p.id for p in projects]
    if not ids:
        return {}
    try:
        current = (await get_embedding_model(session, user_id, require_key=False)).litellm_model
    except ModelUnavailable:
        current = None

    last_runs = await session.execute(
        select(IndexRun.project_id, IndexRun.finished_at, IndexRun.root_path)
        .where(
            IndexRun.user_id == user_id,
            IndexRun.project_id.in_(ids),
            IndexRun.status == IndexRunStatus.SUCCEEDED,
        )
        .order_by(IndexRun.finished_at.desc(), IndexRun.id.desc())
    )
    last: dict[uuid.UUID, Any] = {}
    for row in last_runs:
        last.setdefault(row.project_id, row)  # newest first
    active = dict(
        (
            await session.execute(
                select(IndexRun.project_id, IndexRun.id).where(
                    IndexRun.user_id == user_id,
                    IndexRun.project_id.in_(ids),
                    IndexRun.status.in_((IndexRunStatus.QUEUED, IndexRunStatus.RUNNING)),
                )
            )
        ).all()
    )
    models: dict[uuid.UUID, list[str]] = {}
    for project_id, model in await session.execute(
        select(Chunk.project_id, Chunk.embedding_model)
        .where(Chunk.user_id == user_id, Chunk.project_id.in_(ids))
        .group_by(Chunk.project_id, Chunk.embedding_model)
        .order_by(Chunk.project_id, Chunk.embedding_model)
    ):
        models.setdefault(project_id, []).append(model)
    files = dict(
        (
            await session.execute(
                select(Document.project_id, func.count())
                .where(
                    Document.user_id == user_id,
                    Document.project_id.in_(ids),
                    Document.status == DocumentStatus.INDEXED,
                )
                .group_by(Document.project_id)
            )
        ).all()
    )

    out: dict[uuid.UUID, IndexStatus] = {}
    for project in projects:
        run = last.get(project.id)
        count = int(files.get(project.id, 0))
        indexed = run is not None and count > 0
        project_models = tuple(models.get(project.id, []))
        reasons: list[str] = []
        if indexed:
            if any(m != current for m in project_models):
                reasons.append("embedding_model_changed")
            if run.root_path != project.root_path:
                reasons.append("source_changed")
        out[project.id] = IndexStatus(
            project_id=project.id,
            root_path=project.root_path,
            indexed=indexed,
            last_indexed_at=run.finished_at if indexed else None,
            needs_reindex=bool(reasons),
            reindex_reasons=tuple(reasons),
            embedding_models=project_models,
            files=count,
            active_run_id=active.get(project.id),
        )
    return out


async def index_status(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> IndexStatus:
    project = await get_project(session, user_id, project_id)
    return (await index_status_many(session, user_id, [project]))[project.id]


# ---- source folder ---------------------------------------------------------------------------


async def set_source(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, raw_path: str
) -> IndexStatus:
    """Validate and store the project's folder. Indexed data stays until the next run; a new
    folder makes the project "needs reindex" and is indexed only on an explicit request."""
    await get_project(session, user_id, project_id)
    real = await validate_source_path(raw_path)
    await set_root_path(session, user_id, project_id, real)
    return await index_status(session, user_id, project_id)


# ---- runs and documents ----------------------------------------------------------------------


async def get_run(session: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID) -> IndexRun:
    run = await session.scalar(
        select(IndexRun).where(IndexRun.user_id == user_id, IndexRun.id == run_id)
    )
    if run is None:
        raise NotFound("Index run not found.")
    return run


async def list_runs(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, limit: int = 50
) -> Sequence[IndexRun]:
    await get_project(session, user_id, project_id)
    rows = await session.scalars(
        select(IndexRun)
        .where(IndexRun.user_id == user_id, IndexRun.project_id == project_id)
        .order_by(IndexRun.created_at.desc(), IndexRun.id.desc())
        .limit(limit)
    )
    return rows.all()


async def cancel_run(session: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID) -> IndexRun:
    return await request_cancel(session, await get_run(session, user_id, run_id))


@dataclass(frozen=True)
class DocumentPage:
    items: Sequence[Document]
    total: int
    counts: dict[str, int] = field(default_factory=dict)  # per status


async def list_documents(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    status: DocumentStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> DocumentPage:
    """Indexed and skipped files (with the skip reason), ordered by path."""
    await get_project(session, user_id, project_id)
    where = [Document.user_id == user_id, Document.project_id == project_id]
    counts = dict(
        (
            await session.execute(
                select(Document.status, func.count()).where(*where).group_by(Document.status)
            )
        ).all()
    )
    if status is not None:
        where.append(Document.status == status)
    total = await session.scalar(select(func.count()).select_from(Document).where(*where))
    rows = await session.scalars(
        select(Document).where(*where).order_by(Document.path).limit(limit).offset(offset)
    )
    return DocumentPage(rows.all(), int(total or 0), {str(k): int(v) for k, v in counts.items()})


async def delete_index(session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> int:
    """Remove every file row and chunk of the project (runs stay as history). 409 while a run
    is active. Returns how many file rows were removed."""
    await get_project(session, user_id, project_id)
    if await active_run(session, user_id, project_id) is not None:
        raise IndexInProgress("Cancel the running index first.")
    result = await session.execute(
        delete(Document).where(Document.user_id == user_id, Document.project_id == project_id)
    )
    return result.rowcount or 0


# ---- search and retrieval --------------------------------------------------------------------


def _check_query(query: str) -> str:
    text = query.strip()
    if not text:
        raise InvalidQuery("The query is empty.", details={"field": "query"})
    if len(text) > settings.retrieval_query_max_chars:
        raise InvalidQuery(
            f"The query is longer than {settings.retrieval_query_max_chars} characters.",
            details={"field": "query", "length": len(text)},
        )
    return text


async def _run_search(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    query: str,
    *,
    top_k: int,
    mode: SearchMode,
    path_prefix: str | None,
    language: str | None,
    links: UsageLinks,
) -> list[RetrievedBlock]:
    model = await get_embedding_model(session, user_id)
    vector = None
    if mode != "text":
        [vector] = await gateway.embed(
            session, user_id, model.id, [query],
            trigger=UsageTrigger.USER, links=links, input_type="query",
        )  # fmt: skip
    blocks = await hybrid_search(
        session, user_id, project_id,
        model=model.litellm_model, vector=vector, query=query,
        top_k=min(top_k, settings.retrieval_max_top_k),
        candidates=settings.retrieval_candidates, rrf_k=settings.retrieval_rrf_k,
        mode=mode, path_prefix=path_prefix, language=language,
    )  # fmt: skip
    return [_block(b) for b in blocks]


@dataclass(frozen=True)
class SearchResult:
    blocks: list[RetrievedBlock]
    needs_reindex: bool
    reindex_reasons: tuple[str, ...]


async def search(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    query: str,
    *,
    top_k: int | None = None,
    mode: SearchMode = "hybrid",
    path_prefix: str | None = None,
    language: str | None = None,
) -> SearchResult:
    """The debug search. 422 for an empty or too long query, 409 when nothing is indexed.
    No match is an empty list. Only chunks of the current embedding model are searched."""
    text = _check_query(query)
    status = await index_status(session, user_id, project_id)
    if not status.indexed:
        raise NotIndexed("This project has not been indexed yet. Start an index run first.")
    blocks = await _run_search(
        session, gateway, user_id, project_id, text,
        top_k=top_k or settings.retrieval_top_k, mode=mode,
        path_prefix=path_prefix, language=language,
        links=UsageLinks(project_id=project_id),
    )  # fmt: skip
    return SearchResult(blocks, status.needs_reindex, status.reindex_reasons)


@dataclass(frozen=True)
class RetrievalOutcome:
    blocks: list[RetrievedBlock]
    # Set when retrieval was skipped for a reason the user should know about.
    warning: dict[str, Any] | None = None


async def retrieve_for_context(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    query: str,
    links: UsageLinks,
) -> RetrievalOutcome:
    """Code for the chat context, using `query` (the latest user message).

    Not indexed: nothing, no warning. Needs re-index: nothing, with a warning. Provider errors
    (LLMError) are raised; the caller decides that chat goes on without retrieved code.
    """
    status = await index_status(session, user_id, project_id)
    if not status.indexed:
        return RetrievalOutcome([])
    if status.needs_reindex:
        return RetrievalOutcome(
            [],
            {
                "code": "needs_reindex",
                "message": "Project code was not used: the project needs to be re-indexed.",
                "details": {"reasons": list(status.reindex_reasons)},
            },
        )
    text = query.strip()[: settings.retrieval_query_max_chars]
    if not text:
        return RetrievalOutcome([])
    blocks = await _run_search(
        session, gateway, user_id, project_id, text,
        top_k=settings.retrieval_top_k, mode="hybrid", path_prefix=None, language=None,
        links=links,
    )  # fmt: skip
    return RetrievalOutcome(blocks)


async def blocks_for_chunks(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    refs: Sequence[tuple[uuid.UUID, float | None]],
) -> list[RetrievedBlock]:
    """Blocks for chunk ids recorded earlier (for a preview), with their recorded scores.
    No model call. Chunks deleted since (re-index) are left out."""
    if not refs:
        return []
    scores = {chunk_id: score or 0.0 for chunk_id, score in refs}
    rows = await session.execute(
        select(Chunk, Document.path)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.user_id == user_id,
            Chunk.project_id == project_id,
            Chunk.id.in_(list(scores)),
        )
    )
    hits = [
        Hit(c.id, c.document_id, path, c.start_line, c.end_line, c.language, c.symbol, c.text,
            scores[c.id], None, None)
        for c, path in rows
    ]  # fmt: skip
    return [_block(b) for b in merge_adjacent(hits)]
