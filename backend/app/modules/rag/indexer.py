"""The incremental indexing job, and the estimate that runs before it.

Plan, then embed:
  1. Walk the folder. A file whose size and mtime match its document row (same embedding
     model, fully stored) is unchanged and not read. Otherwise it is read and hashed; the same
     hash only updates the mtime. A changed file is split again.
  2. Each segment has a hash of the text sent to the embedder. A stored chunk with the same
     hash and model keeps its vector, so a small edit re-embeds only the segments it touched,
     and a run that failed halfway re-embeds nothing it already stored.
  3. New segments are embedded in batches (item and token limits). Each batch is one
     transaction. When the last segment of a file is stored, the file is finished: chunks of
     its old content are deleted and its hash is set.
Deleted files lose their rows (and chunks). A rename is a delete plus an add.

Between batches the job pauses (EMBED_BATCH_DELAY_SECONDS) and checks for a cancel request.
RateLimited and ProviderUnavailable are retried with a doubling backoff, or after the
provider's Retry-After when it sends one, up to EMBED_MAX_RETRIES and at most
EMBED_RETRY_MAX_TOTAL_WAIT_SECONDS of waiting per batch; then the run fails and keeps every
finished batch. QuotaExhausted (a daily quota is used up) is never retried: the run fails at
once with "daily_quota_exhausted". Running it again resumes where it stopped.

Logs hold paths, counts and timings only, never file contents.
"""

import asyncio
import hashlib
import logging
import math
import time
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.repositories import UserRepository
from app.modules.llm.service import (
    EmbeddingModelInfo,
    Gateway,
    LLMError,
    ProviderUnavailable,
    QuotaExhausted,
    RateLimited,
    UsageLinks,
    UsageTrigger,
    get_embedding_model,
    get_embedding_model_by_id,
)
from app.modules.projects.service import get_project
from app.modules.rag import secret_scan
from app.modules.rag.chunker import (
    ChunkSettings,
    Segment,
    embedding_input,
    search_text,
    split,
)
from app.modules.rag.models import (
    ACTIVE_RUN_STATUSES,
    Chunk,
    Document,
    DocumentStatus,
    IndexRun,
    IndexRunStatus,
)
from app.modules.rag.scanner import (
    RECORDED_REASONS,
    FileEntry,
    SkipReason,
    SkipReport,
    WalkLimits,
    read_text,
    walk,
)
from app.modules.rag.source import resolve_source_path

logger = logging.getLogger(__name__)

# Replaced in tests, so backoff and batch delays don't slow the suite down.
_sleep = asyncio.sleep

_MTOK = Decimal(1_000_000)


class IndexInProgress(AppError):
    status_code = 409
    code = "index_in_progress"


class CostLimitExceeded(AppError):
    status_code = 409
    code = "cost_limit_exceeded"


class NoSourcePath(AppError):
    status_code = 422
    code = "no_source_path"


class _Cancelled(Exception):
    pass


class _RunError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# Run failure reasons (index_runs.error) set by this file, besides the gateway error codes.
DAILY_QUOTA_EXHAUSTED = "daily_quota_exhausted"
RATE_LIMIT_WAIT_EXCEEDED = "rate_limit_wait_exceeded"


def estimate_tokens(text: str) -> int:
    """About 4 characters per token. Good enough for a cost estimate."""
    return math.ceil(len(text) / 4)


def _cost(tokens: int, model: EmbeddingModelInfo) -> Decimal | None:
    if model.input_cost_per_mtok is None:
        return None
    return (Decimal(tokens) * model.input_cost_per_mtok / _MTOK).quantize(Decimal("0.000001"))


def _now() -> datetime:
    return datetime.now(UTC)


# ---- planning ------------------------------------------------------------------------------


@dataclass
class WorkItem:
    """One segment to store: embedded now, or reusing the vector of `reuse_id`."""

    ordinal: int
    segment: Segment
    embed_text: str
    content_hash: str
    reuse_id: uuid.UUID | None = None


@dataclass
class FilePlan:
    entry: FileEntry
    action: str  # unchanged | touch | index | skip
    document: Document | None
    content_hash: str | None = None
    line_count: int = 0
    fallback: str | None = None
    skip_reason: str | None = None
    items: list[WorkItem] = field(default_factory=list)

    @property
    def to_embed(self) -> list[WorkItem]:
        return [i for i in self.items if i.reuse_id is None]


@dataclass
class Plan:
    files: list[FilePlan]
    skipped: list[tuple[str, str, int]]  # (path, reason, size), recorded per file
    report: SkipReport
    deleted: list[Document]
    files_seen: int
    stopped: str | None = None  # the walk hit INDEX_MAX_ENTRIES: nothing may be changed

    def by_action(self, action: str) -> list[FilePlan]:
        return [f for f in self.files if f.action == action]

    @property
    def to_embed(self) -> list[tuple[FilePlan, WorkItem]]:
        return [(f, i) for f in self.by_action("index") for i in f.to_embed]


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _limit_input(text: str, model: EmbeddingModelInfo) -> str:
    # Stay under the model's input limit; segments are normally far below it.
    max_chars = max(model.max_input_tokens, 1) * 3
    return text[:max_chars]


async def _documents(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> dict[str, Document]:
    rows = await session.scalars(
        select(Document).where(Document.user_id == user_id, Document.project_id == project_id)
    )
    return {d.path: d for d in rows}


async def _reusable(
    session: AsyncSession, user_id: uuid.UUID, document_ids: list[uuid.UUID], model: str
) -> dict[uuid.UUID, dict[str, list[uuid.UUID]]]:
    """document id -> segment hash -> chunk ids stored with `model`."""
    out: dict[uuid.UUID, dict[str, list[uuid.UUID]]] = defaultdict(lambda: defaultdict(list))
    if not document_ids:
        return out
    rows = await session.execute(
        select(Chunk.document_id, Chunk.content_hash, Chunk.id)
        .where(
            Chunk.user_id == user_id,
            Chunk.document_id.in_(document_ids),
            Chunk.embedding_model == model,
        )
        .order_by(Chunk.ordinal, Chunk.id)
    )
    for document_id, content_hash, chunk_id in rows:
        out[document_id][content_hash].append(chunk_id)
    return out


def _unchanged(doc: Document | None, entry: FileEntry, model: str) -> bool:
    """Safe to skip without reading: same size, mtime and model, and checked with the current
    secret rules (otherwise the content is read and checked again)."""
    return (
        doc is not None
        and doc.status == DocumentStatus.INDEXED
        and doc.content_hash is not None
        and doc.embedding_model == model
        and doc.scan_version == secret_scan.RULES_VERSION
        and doc.size_bytes == entry.size
        and doc.mtime_ns == entry.mtime_ns
    )


async def build_plan(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    root: Path,
    model: EmbeddingModelInfo,
) -> Plan:
    """Decide what to do with every file. Reads only files that may have changed."""
    limits = WalkLimits(
        settings.index_max_file_bytes, settings.index_max_files,
        settings.index_max_depth, settings.index_max_entries,
    )  # fmt: skip
    walked = await asyncio.to_thread(walk, root, limits)
    docs = await _documents(session, user_id, project_id)
    cfg = ChunkSettings.from_settings()
    name = model.litellm_model

    plans: list[FilePlan] = []
    skipped = [(s.path, s.reason, s.size) for s in walked.skipped if s.reason in RECORDED_REASONS]
    report = walked.report
    for entry in walked.files:
        doc = docs.get(entry.path)
        if _unchanged(doc, entry, name):
            plans.append(FilePlan(entry, "unchanged", doc))
            continue
        read = await asyncio.to_thread(read_text, entry.abs_path, limits.max_file_bytes)
        if read.text is None:
            assert read.skip_reason is not None
            report.add(read.skip_reason, entry.path)
            skipped.append((entry.path, read.skip_reason, read.size))
            continue
        content_hash = _hash(read.text)
        line_count = read.text.count("\n") + (0 if read.text.endswith("\n") else 1)
        if (
            doc is not None
            and doc.status == DocumentStatus.INDEXED
            and doc.content_hash == content_hash
            and doc.embedding_model == name
        ):
            plans.append(FilePlan(entry, "touch", doc, content_hash, line_count))
            continue
        result = split(read.text, entry.language, cfg)
        if len(result.segments) > settings.index_max_chunks_per_file:
            report.add(SkipReason.TOO_MANY_SEGMENTS, entry.path)
            skipped.append((entry.path, SkipReason.TOO_MANY_SEGMENTS, read.size))
            continue
        items = []
        for ordinal, seg in enumerate(result.segments):
            text = _limit_input(embedding_input(entry.path, seg.symbol, seg.text), model)
            items.append(WorkItem(ordinal, seg, text, _hash(text)))
        plans.append(
            FilePlan(entry, "index", doc, content_hash, line_count, result.fallback, items=items)
        )

    # Reuse vectors already stored for the same segment text and model.
    index_docs = [p.document.id for p in plans if p.action == "index" and p.document]
    reusable = await _reusable(session, user_id, index_docs, name)
    for plan in plans:
        if plan.action != "index" or plan.document is None:
            continue
        pool = reusable.get(plan.document.id, {})
        for item in plan.items:
            ids = pool.get(item.content_hash)
            if ids:
                item.reuse_id = ids.pop(0)

    seen = {p.entry.path for p in plans} | {path for path, _, _ in skipped}
    deleted = [d for path, d in docs.items() if path not in seen]
    files_seen = len(walked.files) + sum(1 for s in walked.skipped if s.reason in RECORDED_REASONS)
    if walked.stopped is not None:
        # A partial walk would count every file it didn't reach as deleted.
        return Plan([], [], report, [], walked.entries_seen, walked.stopped)
    return Plan(plans, skipped, report, deleted, files_seen)


# ---- estimate ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Estimate:
    files_total: int
    files_to_index: int
    files_unchanged: int
    files_skipped: int
    files_deleted: int
    segments_to_embed: int
    segments_reused: int
    tokens: int
    cost_usd: Decimal | None
    provider: str
    model: str
    cost_limit_usd: Decimal
    skip_report: dict[str, Any]

    @property
    def over_limit(self) -> bool:
        return self.cost_usd is not None and self.cost_usd > self.cost_limit_usd

    def as_dict(self) -> dict[str, Any]:
        return {
            "files_total": self.files_total,
            "files_to_index": self.files_to_index,
            "files_unchanged": self.files_unchanged,
            "files_skipped": self.files_skipped,
            "files_deleted": self.files_deleted,
            "segments_to_embed": self.segments_to_embed,
            "segments_reused": self.segments_reused,
            "tokens": self.tokens,
            "cost_usd": str(self.cost_usd) if self.cost_usd is not None else None,
            "cost_limit_usd": str(self.cost_limit_usd),
            "provider": self.provider,
            "model": self.model,
            "skip_report": self.skip_report,
        }


def _estimate(plan: Plan, model: EmbeddingModelInfo) -> Estimate:
    to_embed = plan.to_embed
    tokens = sum(estimate_tokens(item.embed_text) for _, item in to_embed)
    reused = sum(len(f.items) - len(f.to_embed) for f in plan.by_action("index"))
    return Estimate(
        files_total=plan.files_seen,
        files_to_index=len(plan.by_action("index")),
        files_unchanged=len(plan.by_action("unchanged")) + len(plan.by_action("touch")),
        files_skipped=len(plan.skipped),
        files_deleted=len(plan.deleted),
        segments_to_embed=len(to_embed),
        segments_reused=reused,
        tokens=tokens,
        cost_usd=_cost(tokens, model),
        provider=model.provider,
        model=model.litellm_model,
        cost_limit_usd=settings.index_cost_limit_usd,
        skip_report=plan.report.as_dict(),
    )


async def _source_root(session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID) -> Path:
    project = await get_project(session, user_id, project_id)
    if not project.root_path:
        raise NoSourcePath("Set the project's source folder first (PUT /projects/{id}/source).")
    root = Path(project.root_path)
    if not await asyncio.to_thread(root.is_dir):
        raise NoSourcePath(
            "The project's source folder no longer exists.", details={"reason": "missing"}
        )
    # Checked again: the folder may have been saved before a rule existed, or a link in its
    # path may point somewhere else now (audit A-010). 422 invalid_source_path.
    return await asyncio.to_thread(resolve_source_path, project.root_path)


async def estimate_index(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> Estimate:
    """What indexing would do now and roughly what it costs. Reads files; no model call."""
    root = await _source_root(session, user_id, project_id)
    model = await get_embedding_model(session, user_id)
    plan = await build_plan(session, user_id, project_id, root, model)
    return _estimate(plan, model)


# ---- starting, cancelling, recovering ------------------------------------------------------


async def active_run(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> IndexRun | None:
    return await session.scalar(
        select(IndexRun).where(
            IndexRun.user_id == user_id,
            IndexRun.project_id == project_id,
            IndexRun.status.in_(ACTIVE_RUN_STATUSES),
        )
    )


async def start_index(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, *, force: bool = False
) -> IndexRun:
    """Check everything, then create a queued run. The caller commits and starts the job.

    422 without a source folder, embedding model or key; 409 when a run is active, or when the
    estimate is over INDEX_COST_LIMIT_USD and `force` is false.
    """
    root = await _source_root(session, user_id, project_id)
    model = await get_embedding_model(session, user_id)
    if await active_run(session, user_id, project_id) is not None:
        raise IndexInProgress("This project is already being indexed.")
    plan = await build_plan(session, user_id, project_id, root, model)
    estimate = _estimate(plan, model)
    if estimate.over_limit and not force:
        raise CostLimitExceeded(
            f"Indexing would cost about ${estimate.cost_usd}, above the limit of "
            f"${estimate.cost_limit_usd}. Send force=true to index anyway.",
            details={"estimate": estimate.as_dict()},
        )
    run = IndexRun(
        user_id=user_id,
        project_id=project_id,
        status=IndexRunStatus.QUEUED,
        embedding_model_id=model.id,
        embedding_model=model.litellm_model,
        root_path=str(root),
        force=force,
        estimate=estimate.as_dict(),
    )
    session.add(run)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        # Another request created a run between our check and this insert.
        raise IndexInProgress("This project is already being indexed.") from None
    return run


async def request_cancel(session: AsyncSession, run: IndexRun) -> IndexRun:
    """A queued run is cancelled now; a running one stops before its next batch."""
    if run.status == IndexRunStatus.QUEUED:
        run.status = IndexRunStatus.CANCELLED
        run.finished_at = _now()
    elif run.status == IndexRunStatus.RUNNING:
        run.cancel_requested_at = _now()
    await session.flush()
    return run


async def recover_interrupted_runs(session: AsyncSession) -> int:
    """At startup: background jobs die with the server, so a run still queued or running is
    marked failed ("interrupted"). Returns how many were changed. The caller commits."""
    users = await UserRepository(session).list(limit=10_000)
    changed = 0
    for user in users:
        result = await session.execute(
            update(IndexRun)
            .where(IndexRun.user_id == user.id, IndexRun.status.in_(ACTIVE_RUN_STATUSES))
            .values(status=IndexRunStatus.FAILED, error="interrupted", finished_at=_now())
        )
        changed += result.rowcount or 0
    if changed:
        logger.warning("marked %d interrupted index runs as failed", changed)
    return changed


# ---- the job -------------------------------------------------------------------------------


def make_batches(
    items: Sequence[tuple[FilePlan, WorkItem]],
) -> list[list[tuple[FilePlan, WorkItem]]]:
    """Group items by EMBED_BATCH_MAX_ITEMS and EMBED_BATCH_MAX_TOKENS. An item over the
    token limit goes alone."""
    batches: list[list[tuple[FilePlan, WorkItem]]] = []
    current: list[tuple[FilePlan, WorkItem]] = []
    tokens = 0
    for pair in items:
        size = estimate_tokens(pair[1].embed_text)
        if current and (
            len(current) >= settings.embed_batch_max_items
            or tokens + size > settings.embed_batch_max_tokens
        ):
            batches.append(current)
            current, tokens = [], 0
        current.append(pair)
        tokens += size
    if current:
        batches.append(current)
    return batches


async def _embed_with_retry(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    model: EmbeddingModelInfo,
    texts: list[str],
    project_id: uuid.UUID,
) -> list[list[float]]:
    delay = settings.embed_rate_limit_backoff_seconds
    waited = 0.0
    for attempt in range(settings.embed_max_retries + 1):
        try:
            return await gateway.embed(
                session,
                user_id,
                model.id,
                texts,
                trigger=UsageTrigger.USER,
                links=UsageLinks(project_id=project_id),
                input_type="document",
            )
        except QuotaExhausted:
            await session.commit()  # keep the error usage row; waiting can't help
            logger.warning("embedding quota exhausted; stopping the run without retry")
            raise
        except (RateLimited, ProviderUnavailable) as exc:
            await session.commit()  # keep the error usage row
            if attempt == settings.embed_max_retries:
                raise
            asked = exc.retry_after_seconds if isinstance(exc, RateLimited) else None
            wait = asked if asked is not None else delay
            if waited + wait > settings.embed_retry_max_total_wait_seconds:
                logger.warning(
                    "embedding retries stopped code=%s waited_s=%.1f next_wait_s=%.1f",
                    exc.code,
                    waited,
                    wait,
                )
                raise _RunError(RATE_LIMIT_WAIT_EXCEEDED) from None
            logger.warning(
                "embedding batch failed code=%s attempt=%d wait_s=%.1f retry_after=%s",
                exc.code,
                attempt + 1,
                wait,
                asked is not None,
            )
            await _sleep(wait)
            waited += wait
            delay = min(delay * 2, settings.embed_rate_limit_backoff_max_seconds)
    raise AssertionError("unreachable")


def _new_chunk(
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    doc: Document,
    plan: FilePlan,
    item: WorkItem,
    vector: list[float],
    model: EmbeddingModelInfo,
) -> Chunk:
    seg = item.segment
    return Chunk(
        user_id=user_id,
        document_id=doc.id,
        project_id=project_id,
        ordinal=item.ordinal,
        text=seg.text,
        start_line=seg.start_line,
        end_line=seg.end_line,
        token_count=estimate_tokens(seg.text),
        embedding=vector,
        embedding_model=model.litellm_model,
        embedding_dimensions=model.dimensions,
        language=plan.entry.language,
        chunk_type=seg.chunk_type,
        symbol=seg.symbol,
        content_hash=item.content_hash,
        search_text=search_text(plan.entry.path, seg.symbol, seg.text),
    )


async def _finish_file(
    session: AsyncSession,
    user_id: uuid.UUID,
    run: IndexRun,
    plan: FilePlan,
    doc: Document,
    stored: dict[int, uuid.UUID],
    model: EmbeddingModelInfo,
) -> None:
    """Every segment is stored: drop chunks of the old content, fix ordinals and lines of
    reused chunks, and mark the file indexed."""
    keep = {item.reuse_id for item in plan.items if item.reuse_id} | set(stored.values())
    await session.execute(
        delete(Chunk).where(
            Chunk.user_id == user_id, Chunk.document_id == doc.id, Chunk.id.not_in(keep)
        )
    )
    for item in plan.items:
        if item.reuse_id is not None:
            await session.execute(
                update(Chunk)
                .where(Chunk.user_id == user_id, Chunk.id == item.reuse_id)
                .values(
                    ordinal=item.ordinal,
                    start_line=item.segment.start_line,
                    end_line=item.segment.end_line,
                    text=item.segment.text,
                )
            )
    doc.status = DocumentStatus.INDEXED
    doc.skip_reason = None
    doc.content_hash = plan.content_hash
    doc.size_bytes = plan.entry.size
    doc.mtime_ns = plan.entry.mtime_ns
    doc.line_count = plan.line_count
    doc.language = plan.entry.language
    doc.parse_fallback = plan.fallback
    doc.embedding_model = model.litellm_model
    doc.scan_version = secret_scan.RULES_VERSION
    doc.last_index_run_id = run.id
    run.files_indexed += 1


async def _apply_cheap_changes(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, run: IndexRun, plan: Plan
) -> None:
    """Skips, deletes and mtime updates: no model call, one transaction."""
    docs = await _documents(session, user_id, project_id)
    for path, reason, size in plan.skipped:
        doc = docs.get(path)
        if doc is None:
            session.add(
                Document(
                    user_id=user_id,
                    project_id=project_id,
                    path=path,
                    status=DocumentStatus.SKIPPED,
                    skip_reason=reason,
                    size_bytes=size,
                    last_index_run_id=run.id,
                )
            )
            continue
        await session.execute(
            delete(Chunk).where(Chunk.user_id == user_id, Chunk.document_id == doc.id)
        )
        doc.status, doc.skip_reason, doc.size_bytes = DocumentStatus.SKIPPED, reason, size
        doc.content_hash, doc.embedding_model, doc.scan_version = None, None, None
        doc.last_index_run_id = run.id
    for doc in plan.deleted:
        await session.delete(doc)
    for f in plan.by_action("touch"):
        assert f.document is not None
        f.document.size_bytes, f.document.mtime_ns = f.entry.size, f.entry.mtime_ns
        f.document.scan_version = secret_scan.RULES_VERSION  # it was read and checked again
        f.document.last_index_run_id = run.id
    run.files_seen = plan.files_seen
    run.files_skipped = len(plan.skipped)
    run.files_unchanged = len(plan.by_action("unchanged")) + len(plan.by_action("touch"))
    run.skip_report = plan.report.as_dict()
    await session.commit()


async def _execute(
    session: AsyncSession, gateway: Gateway, user_id: uuid.UUID, run: IndexRun
) -> None:
    model = await get_embedding_model_by_id(session, run.embedding_model_id)
    root = Path(run.root_path or "")
    if not run.root_path or not await asyncio.to_thread(root.is_dir):
        raise _RunError("source_missing")
    plan = await build_plan(session, user_id, run.project_id, root, model)
    if plan.stopped is not None:
        run.files_seen, run.skip_report = plan.files_seen, plan.report.as_dict()
        await session.commit()
        logger.warning("index run stopped run=%s reason=%s entries=%d limit=%d", run.id,
                       plan.stopped, plan.files_seen, settings.index_max_entries)  # fmt: skip
        raise _RunError(plan.stopped)
    await _apply_cheap_changes(session, user_id, run.project_id, run, plan)

    # A row for every file that gets segments; new files start as "pending".
    docs: dict[str, Document] = {}
    for f in plan.by_action("index"):
        doc = f.document
        if doc is None:
            doc = Document(
                user_id=user_id,
                project_id=run.project_id,
                path=f.entry.path,
                status=DocumentStatus.PENDING,
                size_bytes=f.entry.size,
                language=f.entry.language,
                last_index_run_id=run.id,
            )
            session.add(doc)
        docs[f.entry.path] = doc
    await session.flush()

    stored: dict[str, dict[int, uuid.UUID]] = defaultdict(dict)
    remaining = {f.entry.path: len(f.to_embed) for f in plan.by_action("index")}
    for f in plan.by_action("index"):
        if remaining[f.entry.path] == 0:
            await _finish_file(session, user_id, run, f, docs[f.entry.path], {}, model)
    await session.commit()

    batches = make_batches(plan.to_embed)
    for number, batch in enumerate(batches):
        await session.refresh(run, ["cancel_requested_at"])
        if run.cancel_requested_at is not None:
            raise _Cancelled
        started = time.monotonic()
        texts = [item.embed_text for _, item in batch]
        vectors = await _embed_with_retry(session, gateway, user_id, model, texts, run.project_id)
        tokens = sum(estimate_tokens(t) for t in texts)
        for (f, item), vector in zip(batch, vectors, strict=True):
            chunk = _new_chunk(user_id, run.project_id, docs[f.entry.path], f, item, vector, model)
            session.add(chunk)
            await session.flush()
            stored[f.entry.path][item.ordinal] = chunk.id
            remaining[f.entry.path] -= 1
            if remaining[f.entry.path] == 0:
                await _finish_file(
                    session, user_id, run, f, docs[f.entry.path], stored[f.entry.path], model
                )
        run.chunks_created += len(batch)
        run.tokens += tokens
        run.cost_estimate_usd = _cost(run.tokens, model)
        await session.commit()
        logger.info(
            "index batch run=%s batch=%d/%d items=%d tokens=%d ms=%d",
            run.id,
            number + 1,
            len(batches),
            len(batch),
            tokens,
            int((time.monotonic() - started) * 1000),
        )
        if number + 1 < len(batches) and settings.embed_batch_delay_seconds:
            await _sleep(settings.embed_batch_delay_seconds)


async def run_index_job(
    session_factory: Any, gateway: Gateway, user_id: uuid.UUID, run_id: uuid.UUID
) -> None:
    """The background task. Never raises: the outcome is stored on the run (rule 55)."""
    async with session_factory() as session:
        run = await session.scalar(
            select(IndexRun).where(IndexRun.user_id == user_id, IndexRun.id == run_id)
        )
        if run is None or run.status != IndexRunStatus.QUEUED:
            return
        run.status = IndexRunStatus.RUNNING
        run.started_at = _now()
        await session.commit()
        started = time.monotonic()
        status, error = IndexRunStatus.SUCCEEDED, None
        try:
            await _execute(session, gateway, user_id, run)
        except _Cancelled:
            status = IndexRunStatus.CANCELLED
        except _RunError as exc:
            status, error = IndexRunStatus.FAILED, exc.code
        except QuotaExhausted:
            status, error = IndexRunStatus.FAILED, DAILY_QUOTA_EXHAUSTED
        except LLMError as exc:
            status, error = IndexRunStatus.FAILED, exc.code
        except Exception as exc:
            # Type only: a message could quote file content.
            logger.error("index run failed run=%s type=%s", run_id, type(exc).__name__)
            status, error = IndexRunStatus.FAILED, "internal_error"
        if not session.is_active or session.in_transaction():
            await session.rollback()
        await session.refresh(run)
        run.status, run.error, run.finished_at = status, error, _now()
        await session.commit()
        logger.info(
            "index run finished run=%s status=%s seen=%d indexed=%d skipped=%d unchanged=%d "
            "segments=%d tokens=%d ms=%d",
            run_id,
            status.value,
            run.files_seen,
            run.files_indexed,
            run.files_skipped,
            run.files_unchanged,
            run.chunks_created,
            run.tokens,
            int((time.monotonic() - started) * 1000),
        )
