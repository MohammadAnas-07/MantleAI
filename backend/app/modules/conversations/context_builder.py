"""ContextBuilder: what we send to a target model, within its token budget.

Sections, most important first:
  1. system prompt (Mantle rules + short project summary), from a versioned prompt file
  2. pinned items (decisions, requirements, open tasks) from the projects module
  3. the rolling conversation summary
  4. recent messages, verbatim
  5. retrieved code from the rag module, as `<source path=... lines=...>` blocks

Budget = context window - reserved output tokens - safety margin (a share of the window).
Retrieved code may use at most RETRIEVED_MAX_SHARE of the budget; the least relevant blocks are
dropped first to stay inside it. When the total is over budget, the lowest-priority content
goes first: retrieved blocks (least relevant first), then the oldest recent messages, then the
summary, then pinned items (tasks, then requirements, then decisions). The system prompt, the
latest user message and the last few turns are never dropped; if even those don't fit,
ContextTooLong is raised.

Pinned items, the summary and retrieved code are untrusted data: they are wrapped in tags, text
inside them that looks like our tags or a chat-template boundary is defanged, and the system
prompt says they are not instructions. This module makes no LLM call and has no I/O. The same
inputs always give the same output.
"""

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.modules.conversations.prompts import SYSTEM_PROMPT, load_prompt
from app.modules.llm.service import ChatMessages, ContextTooLong, ModelInfo
from app.modules.projects.service import DroppedPin, PinnedItem, ProjectInfo, pinned_block
from app.modules.rag.service import RetrievedBlock

TokenCounter = Callable[[ChatMessages], int]

# Our data tags (open and close, also the bare word "retrieved") and common chat-template
# boundaries. Inside data they could end a block early or fake a new turn.
_MARKERS = re.compile(
    r"</?\s*(pinned_items|conversation_summary|retrieved_context|retrieved|source)\b"
    r"|<\||\|>"
    r"|\[/?INST\]"
    r"|<</?SYS>>",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HistoryMessage:
    sequence: int
    role: str  # user | assistant | system | tool
    content: list[dict[str, Any]]  # provider-neutral parts


@dataclass(frozen=True)
class SummaryInput:
    text: str
    from_sequence: int
    to_sequence: int


@dataclass(frozen=True)
class ContextInputs:
    project: ProjectInfo
    # Already selected, ordered and rendered by the projects module (most important first).
    pinned: list[PinnedItem]
    summary: SummaryInput | None
    # Messages NOT covered by the summary, oldest first. The last one is the latest user message.
    history: list[HistoryMessage]
    retrieved: list[RetrievedBlock] = field(default_factory=list)
    # Pinned items the projects module already left out (kind cap, pinned share of the budget).
    pinned_dropped: list[DroppedPin] = field(default_factory=list)


@dataclass(frozen=True)
class BudgetSettings:
    reserved_output_tokens: int
    safety_margin: float
    keep_recent_turns: int
    retrieved_max_share: float = 0.30

    @classmethod
    def from_settings(cls) -> "BudgetSettings":
        return cls(
            reserved_output_tokens=settings.context_reserved_output_tokens,
            safety_margin=settings.context_safety_margin,
            keep_recent_turns=settings.context_keep_recent_turns,
            retrieved_max_share=settings.retrieved_max_share,
        )


@dataclass
class SectionReport:
    name: str  # system | pinned_items | conversation_summary | recent_messages | retrieved_context
    included: bool
    tokens: int
    content: str | ChatMessages
    items_total: int = 0
    items_included: int = 0


@dataclass(frozen=True)
class DroppedBlock:
    block: RetrievedBlock
    reason: str  # share (over the retrieved share) | context_budget (the whole request)


@dataclass
class BuiltContext:
    model: ModelInfo
    messages: ChatMessages
    context_window: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    budget: int
    total_tokens: int
    sections: list[SectionReport]
    dropped: list[str]
    messages_verbatim: int
    first_verbatim_sequence: int | None
    summary_range: tuple[int, int] | None
    summary_tokens: int
    pinned_included: int
    pinned_tokens: int
    # Every pinned item that was left out and why: kind_cap, budget (the pinned share), or
    # context_budget (dropped here because the whole request was too big).
    pinned_dropped: list[DroppedPin]
    retrieved_used: list[RetrievedBlock] = field(default_factory=list)
    retrieved_dropped: list[DroppedBlock] = field(default_factory=list)
    retrieved_tokens: int = 0
    retrieved_max_tokens: int = 0


# ---- tool history conversion -----------------------------------------------------------------


def _text(parts: list[dict[str, Any]]) -> str:
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def to_chat_messages(message: HistoryMessage, supports_tools: bool) -> ChatMessages:
    """One stored message in the target model's format. For models without tool support,
    tool calls and tool results become plain text."""
    parts = message.content
    text = _text(parts)
    calls = [p for p in parts if p.get("type") == "tool_call"]
    results = [p for p in parts if p.get("type") == "tool_result"]

    if supports_tools:
        if message.role == "tool":
            return [
                {"role": "tool", "tool_call_id": r["tool_call_id"], "content": r["content"]}
                for r in results
            ]
        out: dict[str, Any] = {"role": message.role, "content": text}
        if calls:
            out["tool_calls"] = [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {
                        "name": c["name"],
                        "arguments": json.dumps(c.get("arguments", {})),
                    },
                }
                for c in calls
            ]
        return [out]

    lines = [text] if text else []
    for c in calls:
        args = json.dumps(c.get("arguments", {}), sort_keys=True)
        lines.append(f"[Tool call {c['name']}({args}), id {c['id']}]")
    for r in results:
        error = " (error)" if r.get("is_error") else ""
        lines.append(f"[Tool result for {r['tool_call_id']}{error}: {r['content']}]")
    role = "assistant" if message.role == "tool" else message.role
    return [{"role": role, "content": "\n".join(lines)}]


# ---- section text ----------------------------------------------------------------------------


def defang(text: str) -> str:
    """Make tags and chat-template markers inside data harmless: `</source>` becomes
    `&lt;/source&gt;`, `<|im_start|>` becomes `&lt;|im_start|&gt;`, `[INST]` becomes
    `&#91;INST]`. The text stays readable; it just can't close or open a block."""

    def escape(match: re.Match[str]) -> str:
        return match.group(0).replace("<", "&lt;").replace(">", "&gt;").replace("[", "&#91;")

    return _MARKERS.sub(escape, text)


def _attr(value: str) -> str:
    return defang(value).replace("&", "&amp;").replace('"', "&quot;").replace("\n", " ")


def system_text(project: ProjectInfo) -> str:
    description = (project.description or "").strip()[:500]
    return (
        load_prompt(SYSTEM_PROMPT)
        .format(project_name=project.name, project_description=description)
        .strip()
    )


def pinned_text(items: list[PinnedItem]) -> str:
    # Rendered and defanged by the projects module (projects/pinned.py).
    return pinned_block(items)


def summary_text(summary: SummaryInput | None) -> str:
    if summary is None:
        return ""
    covers = f"messages {summary.from_sequence}-{summary.to_sequence}"
    return (
        f'<conversation_summary covers="{covers}">\n'
        + defang(summary.text.strip())
        + "\n</conversation_summary>"
    )


def source_block(block: RetrievedBlock) -> str:
    """One retrieved block: where it is from, then the code as data."""
    attrs = f'path="{_attr(block.path)}" lines="{block.start_line}-{block.end_line}"'
    if block.symbol:
        attrs += f' symbol="{_attr(block.symbol)}"'
    if block.language:
        attrs += f' language="{_attr(block.language)}"'
    return f"<source {attrs}>\n{defang(block.text)}\n</source>"


def retrieved_text(blocks: list[RetrievedBlock]) -> str:
    if not blocks:
        return ""
    body = "\n".join(source_block(b) for b in blocks)
    return f"<retrieved_context>\n{body}\n</retrieved_context>"


def relevance_order(blocks: list[RetrievedBlock]) -> list[RetrievedBlock]:
    """Most relevant first; ties broken by path and line so the order never depends on input
    order."""
    return sorted(blocks, key=lambda b: (-b.score, b.path, b.start_line, b.end_line))


def _label(block: RetrievedBlock) -> str:
    return f"retrieved {block.path}:{block.start_line}-{block.end_line}"


# ---- the builder -----------------------------------------------------------------------------


def compute_budget(model: ModelInfo, budget: BudgetSettings) -> tuple[int, int, int]:
    """(budget, reserved output, safety margin) in tokens."""
    reserved = budget.reserved_output_tokens
    if model.max_output_tokens:
        reserved = min(reserved, model.max_output_tokens)
    margin = math.ceil(model.context_window * budget.safety_margin)
    return model.context_window - reserved - margin, reserved, margin


def required_start(history: list[HistoryMessage], keep_recent_turns: int) -> int:
    """Index of the first message that must be kept: the latest user message plus
    `keep_recent_turns` user turns before it, with everything after them."""
    user_positions = [i for i, m in enumerate(history) if m.role == "user"]
    if not user_positions:
        return max(len(history) - 1, 0)
    keep = user_positions[-(keep_recent_turns + 1) :]
    return keep[0]


class ContextBuilder:
    def __init__(self, count: TokenCounter, budget: BudgetSettings | None = None) -> None:
        self.count = count
        self.budget_settings = budget or BudgetSettings.from_settings()

    def _tokens(self, text: str) -> int:
        return self.count([{"role": "system", "content": text}]) if text else 0

    def build(self, model: ModelInfo, inputs: ContextInputs) -> BuiltContext:
        budget, reserved, margin = compute_budget(model, self.budget_settings)

        converted = [to_chat_messages(m, model.supports_tools) for m in inputs.history]
        msg_tokens = [self.count(msgs) if msgs else 0 for msgs in converted]
        required = required_start(inputs.history, self.budget_settings.keep_recent_turns)

        base = system_text(inputs.project)
        dropped: list[str] = []

        # Retrieved code: its own share of the budget, least relevant dropped first.
        retrieved = relevance_order(inputs.retrieved)
        retrieved_dropped: list[DroppedBlock] = []
        retrieved_max = max(int(budget * self.budget_settings.retrieved_max_share), 0)
        while retrieved and self._tokens(retrieved_text(retrieved)) > retrieved_max:
            block = retrieved.pop()
            retrieved_dropped.append(DroppedBlock(block, "share"))
            dropped.append(_label(block))

        use_summary = inputs.summary is not None
        pinned_kept = len(inputs.pinned)
        first_kept = 0  # index of the oldest history message still included

        def system_message() -> str:
            blocks = [
                base,
                pinned_text(inputs.pinned[:pinned_kept]),
                summary_text(inputs.summary) if use_summary else "",
                retrieved_text(retrieved),
            ]
            return "\n\n".join(b for b in blocks if b)

        def assemble() -> ChatMessages:
            messages: ChatMessages = [{"role": "system", "content": system_message()}]
            for msgs in converted[first_kept:]:
                messages.extend(msgs)
            return messages

        def estimate() -> int:
            system_tokens = self.count([{"role": "system", "content": system_message()}])
            return system_tokens + sum(msg_tokens[first_kept:])

        def drop_next() -> bool:
            nonlocal use_summary, pinned_kept, first_kept
            if retrieved:
                block = retrieved.pop()
                retrieved_dropped.append(DroppedBlock(block, "context_budget"))
                dropped.append(_label(block))
                return True
            if first_kept < required:
                dropped.append(f"message #{inputs.history[first_kept].sequence}")
                first_kept += 1
                return True
            if use_summary:
                use_summary = False
                dropped.append("conversation_summary")
                return True
            if pinned_kept > 0:
                pinned_kept -= 1
                item = inputs.pinned[pinned_kept]
                dropped.append(f"pinned {item.kind} {item.id.hex[:8]}")
                return True
            return False

        # Fast pass on per-section estimates, then confirm with a real count of the whole request.
        total = estimate()
        while True:
            while total > budget:
                if not drop_next():
                    raise ContextTooLong(
                        "Even the system prompt and the latest messages don't fit this model.",
                        details={
                            "model_id": str(model.id),
                            "budget": budget,
                            "required_tokens": total,
                        },
                    )
                total = estimate()
            messages = assemble()
            total = self.count(messages)
            if total <= budget:
                break

        sections = self._report(inputs, base, retrieved, use_summary, pinned_kept,
                                converted[first_kept:])  # fmt: skip
        included = inputs.history[first_kept:]
        summary = inputs.summary if use_summary else None
        pinned_dropped = list(inputs.pinned_dropped) + [
            DroppedPin(p.id, p.kind, "context_budget") for p in inputs.pinned[pinned_kept:]
        ]
        return BuiltContext(
            model=model,
            messages=messages,
            context_window=model.context_window,
            reserved_output_tokens=reserved,
            safety_margin_tokens=margin,
            budget=budget,
            total_tokens=total,
            sections=sections,
            dropped=dropped,
            messages_verbatim=len(included),
            first_verbatim_sequence=included[0].sequence if included else None,
            summary_range=(summary.from_sequence, summary.to_sequence) if summary else None,
            summary_tokens=next(s.tokens for s in sections if s.name == "conversation_summary"),
            pinned_included=pinned_kept,
            pinned_tokens=next(s.tokens for s in sections if s.name == "pinned_items"),
            pinned_dropped=pinned_dropped,
            retrieved_used=list(retrieved),
            retrieved_dropped=retrieved_dropped,
            retrieved_tokens=next(s.tokens for s in sections if s.name == "retrieved_context"),
            retrieved_max_tokens=retrieved_max,
        )

    def _report(
        self,
        inputs: ContextInputs,
        base: str,
        retrieved: list[RetrievedBlock],
        use_summary: bool,
        pinned_kept: int,
        recent: list[ChatMessages],
    ) -> list[SectionReport]:
        tokens = self._tokens
        pinned = pinned_text(inputs.pinned[:pinned_kept])
        summary = summary_text(inputs.summary) if use_summary else ""
        retrieved_section = retrieved_text(retrieved)
        recent_flat = [m for msgs in recent for m in msgs]
        return [
            SectionReport("system", True, tokens(base), base),
            SectionReport("pinned_items", pinned_kept > 0, tokens(pinned), pinned,
                          len(inputs.pinned), pinned_kept),
            SectionReport("conversation_summary", use_summary, tokens(summary), summary,
                          1 if inputs.summary else 0, 1 if use_summary else 0),
            SectionReport("recent_messages", bool(recent), self.count(recent_flat) if recent else 0,
                          recent_flat, len(inputs.history), len(recent)),
            SectionReport("retrieved_context", bool(retrieved), tokens(retrieved_section),
                          retrieved_section, len(inputs.retrieved), len(retrieved)),
        ]  # fmt: skip
