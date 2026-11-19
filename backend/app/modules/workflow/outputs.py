"""Model output for the gap finder, Planner and Reviewer: parse, validate, check references.

Model output is untrusted. It is parsed as JSON, validated with Pydantic, and only then stored
as a draft. Nothing in it is ever executed or followed. References to memory items that the
project doesn't have are dropped with a warning, so a stored result never names an id that
doesn't exist. No I/O, no LLM.
"""

import json
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings

Severity = Literal["low", "medium", "high"]

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_MAX_TEXT = 4000  # explanation, description and similar free text


class OutputInvalid(ValueError):
    """The model's answer can't be used. The message is short and safe to send back to the
    model in a retry, and to store on the run: it names fields, never quotes the output."""


def extract_json(text: str) -> Any:
    """The JSON object in a model reply: inside a ```json fence, or the first {...} in the
    text (models often add a sentence before or after)."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        start = candidate.find("{")
        while start != -1:
            try:
                value, _ = decoder.raw_decode(candidate, start)
            except ValueError:
                start = candidate.find("{", start + 1)
                continue
            if isinstance(value, dict):
                return value
            start = candidate.find("{", start + 1)
    raise OutputInvalid("The answer contains no JSON object.")


def _errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:10]:
        where = ".".join(str(p) for p in err["loc"]) or "(root)"
        parts.append(f"{where}: {err['msg']}")
    return "; ".join(parts)


def parse[M: BaseModel](text: str, model: type[M]) -> M:
    """Extract and validate. OutputInvalid names what is wrong."""
    data = extract_json(text)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise OutputInvalid(f"The JSON doesn't match the schema: {_errors(exc)}") from None


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


def _title(value: str) -> str:
    text = " ".join(value.split())
    if not text:
        raise ValueError("must not be empty")
    if len(text) > settings.memory_title_max_length:
        raise ValueError(f"must be at most {settings.memory_title_max_length} characters")
    return text


def _text(value: str, limit: int = _MAX_TEXT) -> str:
    text = value.strip()
    if len(text) > limit:
        raise ValueError(f"must be at most {limit} characters")
    return text


def _short_text(value: str) -> str:
    return _text(value, 500)


# Same limits as memory items typed by hand (MEMORY_TITLE_MAX_LENGTH).
Title = Annotated[str, AfterValidator(_title)]
Text = Annotated[str, AfterValidator(_text)]
ShortText = Annotated[str, AfterValidator(_short_text)]


# ---- gap finder -----------------------------------------------------------------------------


class Finding(_Out):
    title: Title
    explanation: Text
    severity: Severity
    refers_to: list[str] = Field(default_factory=list, max_length=20)


class GapReport(_Out):
    missing_steps: list[Finding] = Field(default_factory=list, max_length=20)
    risks: list[Finding] = Field(default_factory=list, max_length=20)
    technical_debt: list[Finding] = Field(default_factory=list, max_length=20)
    scalability_concerns: list[Finding] = Field(default_factory=list, max_length=20)

    def findings(self) -> Iterable[tuple[str, Finding]]:
        for name in ("missing_steps", "risks", "technical_debt", "scalability_concerns"):
            for finding in getattr(self, name):
                yield name, finding


# ---- planner --------------------------------------------------------------------------------


class ProposedTask(_Out):
    title: Title
    description: Text = ""
    priority: Literal["high", "medium", "low"] = "medium"
    acceptance_criteria: list[ShortText] = Field(default_factory=list, max_length=20)
    depends_on: list[int] = Field(default_factory=list, max_length=30)
    # Set by flag_duplicates after validation; whatever the model sent is overwritten.
    possible_duplicate_of: str | None = None

    def body(self) -> str:
        """The memory item body: the description, then the acceptance criteria."""
        parts = [self.description] if self.description else []
        if self.acceptance_criteria:
            parts.append(
                "Acceptance criteria:\n" + "\n".join(f"- {c}" for c in self.acceptance_criteria)
            )
        return "\n\n".join(parts)


class ProposedDecision(_Out):
    title: Title
    what: Text
    why: Text = ""
    alternatives: Text = ""


class Plan(_Out):
    tasks: list[ProposedTask] = Field(default_factory=list)
    decisions: list[ProposedDecision] = Field(default_factory=list)
    assumptions: list[ShortText] = Field(default_factory=list, max_length=30)
    risks: list[ShortText] = Field(default_factory=list, max_length=30)
    open_questions: list[ShortText] = Field(default_factory=list, max_length=30)


def check_plan(plan: Plan) -> None:
    """Rules Pydantic can't express. OutputInvalid explains the first problem found."""
    total = len(plan.tasks) + len(plan.decisions)
    if total == 0:
        raise OutputInvalid("The plan has no tasks and no decisions.")
    if total > settings.agent_plan_max_items:
        raise OutputInvalid(
            f"The plan has {total} tasks and decisions; at most "
            f"{settings.agent_plan_max_items} are allowed."
        )
    count = len(plan.tasks)
    for i, task in enumerate(plan.tasks):
        for dep in task.depends_on:
            if dep == i:
                raise OutputInvalid(f"tasks.{i} depends on itself.")
            if not 0 <= dep < count:
                raise OutputInvalid(f"tasks.{i}.depends_on has {dep}, which is not a task index.")
    cycle = find_cycle([t.depends_on for t in plan.tasks])
    if cycle:
        raise OutputInvalid(f"The task dependencies have a cycle: {' -> '.join(map(str, cycle))}.")


def find_cycle(edges: list[list[int]]) -> list[int] | None:
    """A cycle in "task i depends on edges[i]", as a list of indexes, or None."""
    state = [0] * len(edges)  # 0 new, 1 on the stack, 2 done
    for root in range(len(edges)):
        if state[root]:
            continue
        stack: list[tuple[int, int]] = [(root, 0)]
        path: list[int] = []
        while stack:
            node, next_child = stack.pop()
            if next_child == 0:
                state[node] = 1
                path.append(node)
            children = edges[node]
            if next_child < len(children):
                stack.append((node, next_child + 1))
                child = children[next_child]
                if state[child] == 1:
                    return path[path.index(child) :] + [child]
                if state[child] == 0:
                    stack.append((child, 0))
            else:
                state[node] = 2
                path.pop()
    return None


def flag_duplicates(plan: Plan, existing_tasks: dict[str, uuid.UUID]) -> None:
    """Mark proposed tasks whose title matches an existing task (case-insensitive). They are
    kept: the user decides."""
    for task in plan.tasks:
        match = existing_tasks.get(task.title.casefold())
        task.possible_duplicate_of = str(match) if match else None


# ---- reviewer -------------------------------------------------------------------------------


class ReviewFinding(_Out):
    severity: Severity
    refers_to: list[str] = Field(default_factory=list, max_length=20)
    explanation: Text
    suggestion: Text = ""


class Review(_Out):
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=30)
    verdict: Literal["approve", "changes_requested"]


# ---- references ------------------------------------------------------------------------------


@dataclass
class References:
    """Ids a result may point at: memory items (full or 8-character id) and, for a plan run,
    items of the draft plan ("task:N", "decision:N")."""

    memory: dict[str, uuid.UUID] = field(default_factory=dict)  # short or full id -> id
    plan_items: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, memory_ids: Iterable[uuid.UUID], plan: Plan | None = None) -> "References":
        refs = cls()
        for item_id in memory_ids:
            refs.memory[str(item_id)] = item_id
            refs.memory[item_id.hex[:8]] = item_id
        if plan is not None:
            refs.plan_items |= {f"task:{i}" for i in range(len(plan.tasks))}
            refs.plan_items |= {f"decision:{i}" for i in range(len(plan.decisions))}
        return refs

    def resolve(self, ref: str) -> str | None:
        key = ref.strip().lower()
        if key in self.plan_items:
            return key
        found = self.memory.get(key)
        return str(found) if found else None


def check_references(items: Iterable[tuple[str, Any]], refs: References) -> list[dict[str, Any]]:
    """Replace each item's `refers_to` with full, existing ids; drop the rest. Returns one
    warning per dropped reference (never the reference text itself when it is long)."""
    warnings: list[dict[str, Any]] = []
    for where, item in items:
        kept: list[str] = []
        for ref in item.refers_to:
            resolved = refs.resolve(ref)
            if resolved is None:
                warnings.append(
                    {"code": "unknown_reference", "where": where, "reference": ref[:40]}
                )
            elif resolved not in kept:
                kept.append(resolved)
        item.refers_to = kept
    return warnings
