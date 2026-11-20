"""Which memory items are pinned into a model's context, and their text. No I/O, no LLM.

Order: accepted decisions, then approved must and should requirements, then open tasks
(in_progress, todo, blocked; higher priority first). Inside a group: created_at, then id.
Superseded, rejected, deprecated, proposed, dropped, draft, could-have and done items are never
pinned.

The text is deterministic (same items give byte-identical text) so provider prompt caching can
reuse it. Item text is user-authored but may hold pasted content, so anything that looks like our
data delimiters or a chat-template boundary is defanged, and each item is one line.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import settings
from app.core.prompt_data import defang

TRUNCATED = " [truncated]"
_OPEN, _CLOSE = "<pinned_items>", "</pinned_items>"

_GROUPS = ("decision", "requirement", "task")
_STATUS_RANK = {
    "decision": {"accepted": 0},
    "requirement": {"approved": 0},
    "task": {"in_progress": 0, "todo": 1, "blocked": 2},
}
_PRIORITY_RANK = {
    "decision": {None: 0},
    "requirement": {"must": 0, "should": 1},
    "task": {"high": 0, "medium": 1, "low": 2, None: 3},
}

# Our own data tags; app.core.prompt_data also covers chat-template boundaries.
_TAGS = ("pinned_items", "conversation_summary", "retrieved_context", "source", "project_memory")


class MemoryRow(Protocol):
    """The attributes pinning reads from a memory item."""

    id: uuid.UUID
    kind: Any
    title: str
    status: Any
    priority: Any
    body: str
    why: str | None
    alternatives: str | None
    created_at: Any


@dataclass(frozen=True)
class PinnedItem:
    id: uuid.UUID
    kind: str
    status: str
    line: str


@dataclass(frozen=True)
class DroppedPin:
    id: uuid.UUID
    kind: str
    reason: str  # kind_cap | budget


@dataclass
class PinnedSelection:
    items: list[PinnedItem] = field(default_factory=list)
    dropped: list[DroppedPin] = field(default_factory=list)
    tokens: int = 0


def neutralize(text: str) -> str:
    """Defang delimiters and chat-template markers with the shared helper; ordinary `<` and
    `>` stay as they are."""
    return defang(text, _TAGS)


def _one_line(text: str) -> str:
    return " / ".join(part.strip() for part in text.splitlines() if part.strip()).replace("\t", " ")


def render(row: MemoryRow) -> str:
    kind, status = str(row.kind), str(row.status)
    tags = [kind, row.id.hex[:8], status] + ([str(row.priority)] if row.priority else [])
    content = row.title + (f": {row.body}" if row.body else "")
    extras = [f"why: {row.why}"] if row.why else []
    extras += [f"alternatives: {row.alternatives}"] if row.alternatives else []
    text = _one_line(neutralize(" | ".join([content, *extras])))
    limit = settings.pinned_item_max_chars
    prefix = f"- [{' '.join(tags)}] "
    if len(prefix) + len(text) > limit:
        text = text[: max(limit - len(prefix), 0)].rstrip() + TRUNCATED
    return prefix + text


def pinned_block(items: Sequence[PinnedItem]) -> str:
    """The section as it goes into the system prompt; empty when nothing is pinned."""
    if not items:
        return ""
    return _OPEN + "\n" + "\n".join(i.line for i in items) + "\n" + _CLOSE


def _sort_key(row: MemoryRow) -> tuple[Any, ...]:
    kind = str(row.kind)
    priority = str(row.priority) if row.priority else None
    return (
        _GROUPS.index(kind),
        _STATUS_RANK[kind][str(row.status)],
        _PRIORITY_RANK[kind].get(priority, 99),
        row.created_at,
        row.id,
    )


def _eligible(row: MemoryRow) -> bool:
    kind = str(row.kind)
    if kind not in _STATUS_RANK or str(row.status) not in _STATUS_RANK[kind]:
        return False
    priority = str(row.priority) if row.priority else None
    return priority in _PRIORITY_RANK[kind]


def select_pinned(
    rows: Sequence[MemoryRow], *, max_tokens: int, count: Callable[[str], int]
) -> PinnedSelection:
    """Pick and render pinned items within `max_tokens` (counted with `count`).

    Items past a kind's cap are dropped with reason `kind_cap`. Then items are added in priority
    order until the next one doesn't fit; it and everything after it are dropped (`budget`), so
    only the lowest-priority items are ever left out.
    """
    caps = {
        "decision": settings.pinned_max_decisions,
        "requirement": settings.pinned_max_requirements,
        "task": settings.pinned_max_tasks,
    }
    ordered = sorted((r for r in rows if _eligible(r)), key=_sort_key)
    selection = PinnedSelection()
    kept: list[MemoryRow] = []
    used = dict.fromkeys(caps, 0)
    for row in ordered:
        kind = str(row.kind)
        if used[kind] >= caps[kind]:
            selection.dropped.append(DroppedPin(row.id, kind, "kind_cap"))
            continue
        used[kind] += 1
        kept.append(row)

    candidates = [PinnedItem(r.id, str(r.kind), str(r.status), render(r)) for r in kept]
    # Per-line counts overestimate (each carries message overhead), so the sum is a safe bound;
    # the whole block is counted again at the end.
    total = count(_OPEN + "\n\n" + _CLOSE)
    fits = 0
    for candidate in candidates:
        cost = count(candidate.line)
        if total + cost > max_tokens:
            break
        total += cost
        fits += 1
    while fits and count(pinned_block(candidates[:fits])) > max_tokens:
        fits -= 1
    selection.items = candidates[:fits]
    selection.dropped += [DroppedPin(c.id, c.kind, "budget") for c in candidates[fits:]]
    selection.tokens = count(pinned_block(selection.items)) if selection.items else 0
    return selection
