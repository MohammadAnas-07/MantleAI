"""Hybrid search over a project's chunks: vector similarity plus full-text, fused with
reciprocal rank fusion (RRF).

Each arm returns its best `RETRIEVAL_CANDIDATES` chunks, filtered by user, project and the
current embedding model (vectors of different models are never compared) and, optionally, by
path prefix and language. RRF gives a chunk 1 / (k + rank) per arm it appears in, k = 60, and
sums them. Overlapping or adjacent chunks of one file are then merged into one block.

Full-text search uses the 'simple' configuration (no stemming, no stop words) on `search_text`,
where identifiers are split into words; the query's words are OR-ed, so a long question still
matches code that has only some of its words.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rag.chunker import split_identifier
from app.modules.rag.models import Chunk, Document

SearchMode = Literal["hybrid", "vector", "text"]

# Words too common to help a full-text match. Short on purpose.
_STOP_WORDS = frozenset(
    "a an and are as at be by do does for from how i in is it of on or set the this to was "
    "what when where which who why with".split()
)
_WORD = re.compile(r"[A-Za-z0-9_]+")


def query_terms(query: str) -> list[str]:
    """Lowercase search words of a query, identifiers split, stop words removed, in order."""
    out: list[str] = []
    for word in _WORD.findall(query):
        for term in [word.lower(), *split_identifier(word)]:
            if term not in _STOP_WORDS and term not in out:
                out.append(term)
    return out


@dataclass(frozen=True)
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    path: str
    start_line: int
    end_line: int
    language: str | None
    symbol: str | None
    text: str
    score: float  # fused RRF score
    vector_rank: int | None  # 1-based rank in each arm, None when not in that arm
    text_rank: int | None


@dataclass
class Block:
    """One or more merged hits from the same file."""

    path: str
    start_line: int
    end_line: int
    language: str | None
    symbol: str | None
    text: str
    score: float
    vector_rank: int | None
    text_rank: int | None
    chunk_ids: list[uuid.UUID] = field(default_factory=list)


def _filtered(
    stmt: Select,  # type: ignore[type-arg]
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    model: str,
    path_prefix: str | None,
    language: str | None,
) -> Select:  # type: ignore[type-arg]
    stmt = stmt.where(
        Chunk.user_id == user_id,
        Chunk.project_id == project_id,
        Chunk.embedding_model == model,
    )
    if path_prefix:
        escaped = path_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.join(Document, Document.id == Chunk.document_id).where(
            Document.user_id == user_id, Document.path.like(f"{escaped}%", escape="\\")
        )
    if language:
        stmt = stmt.where(Chunk.language == language)
    return stmt


async def vector_ranking(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    model: str,
    vector: list[float],
    limit: int,
    path_prefix: str | None = None,
    language: str | None = None,
) -> list[uuid.UUID]:
    """Chunk ids, nearest first (cosine distance)."""
    # With filters, an HNSW scan can stop before it finds `limit` matching rows; the iterative
    # scan (pgvector 0.8+) keeps going.
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    distance = Chunk.embedding.cosine_distance(vector)
    stmt = _filtered(select(Chunk.id, distance.label("d")), user_id, project_id, model,
                     path_prefix, language)  # fmt: skip
    rows = await session.execute(stmt.order_by(distance, Chunk.id).limit(limit))
    # relaxed_order may return rows slightly out of order; sort again.
    return [r.id for r in sorted(rows, key=lambda r: (r.d, str(r.id)))]


async def text_ranking(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    model: str,
    query: str,
    limit: int,
    path_prefix: str | None = None,
    language: str | None = None,
) -> list[uuid.UUID]:
    """Chunk ids, best full-text match first. Empty when the query has no usable words."""
    terms = query_terms(query)
    if not terms:
        return []
    tsquery = func.to_tsquery("simple", " | ".join(terms))
    rank = func.ts_rank_cd(Chunk.search_tsv, tsquery)
    stmt = _filtered(select(Chunk.id), user_id, project_id, model, path_prefix, language)
    stmt = stmt.where(Chunk.search_tsv.op("@@")(tsquery))
    rows = await session.execute(stmt.order_by(rank.desc(), Chunk.id).limit(limit))
    return [r.id for r in rows]


def fuse(rankings: list[list[uuid.UUID]], k: int) -> dict[uuid.UUID, float]:
    """Reciprocal rank fusion: the sum of 1 / (k + rank) over the rankings."""
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


async def load_hits(
    session: AsyncSession,
    user_id: uuid.UUID,
    scores: dict[uuid.UUID, float],
    vector_ids: list[uuid.UUID],
    text_ids: list[uuid.UUID],
) -> list[Hit]:
    """Hits for the scored chunk ids, best first; ties broken by path and line."""
    if not scores:
        return []
    rows = await session.execute(
        select(Chunk, Document.path)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.user_id == user_id, Chunk.id.in_(list(scores)))
    )
    v_rank = {cid: i for i, cid in enumerate(vector_ids, start=1)}
    t_rank = {cid: i for i, cid in enumerate(text_ids, start=1)}
    hits = [
        Hit(
            chunk_id=c.id,
            document_id=c.document_id,
            path=path,
            start_line=c.start_line,
            end_line=c.end_line,
            language=c.language,
            symbol=c.symbol,
            text=c.text,
            score=scores[c.id],
            vector_rank=v_rank.get(c.id),
            text_rank=t_rank.get(c.id),
        )
        for c, path in rows
    ]
    return sorted(hits, key=lambda h: (-h.score, h.path, h.start_line))


def _min(a: int | None, b: int | None) -> int | None:
    values = [v for v in (a, b) if v is not None]
    return min(values) if values else None


def _whole_lines(hit: Hit) -> bool:
    """False for a piece of one very long line (its text is not the whole line range)."""
    return hit.text.count("\n") == hit.end_line - hit.start_line


# Hits this many lines apart still merge. The chunker leaves out only blank lines between
# definitions (Python puts two between top-level ones), so a gap this small is blank.
MERGE_GAP_LINES = 2


def merge_adjacent(hits: list[Hit]) -> list[Block]:
    """Merge hits of the same file whose line ranges overlap, touch, or are separated by at
    most MERGE_GAP_LINES blank lines. A block keeps the best score and ranks of its hits;
    blocks are ordered by score, then path and line."""
    by_file: dict[str, list[Hit]] = {}
    for hit in hits:
        by_file.setdefault(hit.path, []).append(hit)
    blocks: list[Block] = []
    for path, file_hits in by_file.items():
        file_hits.sort(key=lambda h: (h.start_line, h.end_line))
        current: Block | None = None
        lines: dict[int, str] = {}
        for hit in file_hits:
            if (
                current is not None
                and _whole_lines(hit)
                and hit.start_line <= current.end_line + 1 + MERGE_GAP_LINES
            ):
                for gap in range(current.end_line + 1, hit.start_line):
                    lines[gap] = ""
                lines.update(enumerate(hit.text.split("\n"), start=hit.start_line))
                current.end_line = max(current.end_line, hit.end_line)
                current.score = max(current.score, hit.score)
                current.vector_rank = _min(current.vector_rank, hit.vector_rank)
                current.text_rank = _min(current.text_rank, hit.text_rank)
                current.symbol = current.symbol or hit.symbol
                current.chunk_ids.append(hit.chunk_id)
                current.text = "\n".join(lines[n] for n in sorted(lines))
                continue
            current = Block(path, hit.start_line, hit.end_line, hit.language, hit.symbol,
                            hit.text, hit.score, hit.vector_rank, hit.text_rank,
                            [hit.chunk_id])  # fmt: skip
            blocks.append(current)
            if _whole_lines(hit):
                lines = dict(enumerate(hit.text.split("\n"), start=hit.start_line))
            else:
                current = None  # never merge into a piece of a long line
    return sorted(blocks, key=lambda b: (-b.score, b.path, b.start_line))


async def hybrid_search(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    model: str,
    vector: list[float] | None,
    query: str,
    top_k: int,
    candidates: int,
    rrf_k: int,
    mode: SearchMode = "hybrid",
    path_prefix: str | None = None,
    language: str | None = None,
) -> list[Block]:
    """The `top_k` best chunks, merged into blocks. `vector` may be None for mode "text"."""
    vector_ids: list[uuid.UUID] = []
    text_ids: list[uuid.UUID] = []
    if mode in ("hybrid", "vector") and vector is not None:
        vector_ids = await vector_ranking(session, user_id, project_id, model, vector,
                                          candidates, path_prefix, language)  # fmt: skip
    if mode in ("hybrid", "text"):
        text_ids = await text_ranking(session, user_id, project_id, model, query,
                                      candidates, path_prefix, language)  # fmt: skip
    scores = fuse([vector_ids, text_ids], rrf_k)
    hits = await load_hits(session, user_id, scores, vector_ids, text_ids)
    return merge_adjacent(hits[:top_k])
