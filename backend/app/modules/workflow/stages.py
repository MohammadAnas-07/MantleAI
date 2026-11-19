"""The workflow stage definitions from `stages.yaml`, checked once when the API starts.

A bad file must stop the app with a message that names the problem, not fail later in a
request. No I/O except reading the file; no LLM.
"""

from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

STAGES_FILE = Path(__file__).resolve().parent / "stages.yaml"

MEMORY_KINDS = {"requirement", "decision", "task"}
# Statuses per kind, as in docs/data-model.md (projects owns them; repeated here as plain
# strings so a typo in the YAML is caught at startup).
MEMORY_STATUSES = {
    "requirement": {"draft", "approved", "dropped"},
    "decision": {"proposed", "accepted", "rejected", "deprecated", "superseded"},
    "task": {"todo", "in_progress", "done", "blocked"},
}


class StageConfigError(Exception):
    """The stage file is missing or invalid. The message says what to fix."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChecklistItem(_Strict):
    id: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    text: str = Field(min_length=1)
    required: bool


class MemoryCountRule(_Strict):
    """At least `min` memory items of `kind`, limited to `statuses` when given."""

    type: Literal["min_memory_items"]
    kind: str
    statuses: tuple[str, ...] = ()
    min: int = Field(ge=1)
    text: str = Field(min_length=1)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in MEMORY_KINDS:
            raise ValueError(f"unknown memory kind {value!r}; use one of {sorted(MEMORY_KINDS)}")
        return value

    def unknown_statuses(self) -> list[str]:
        return [s for s in self.statuses if s not in MEMORY_STATUSES[self.kind]]


class StageDefinition(_Strict):
    id: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    title: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    checklist: tuple[ChecklistItem, ...] = Field(min_length=1)
    artifacts: tuple[MemoryCountRule, ...] = ()

    def item(self, item_id: str) -> ChecklistItem | None:
        return next((i for i in self.checklist if i.id == item_id), None)


class _StageFile(_Strict):
    stages: tuple[StageDefinition, ...] = Field(min_length=1)


class StageList:
    """The stages in order, with lookups by id."""

    def __init__(self, stages: tuple[StageDefinition, ...]) -> None:
        self.stages = stages
        self._by_id = {s.id: s for s in stages}

    def get(self, stage_id: str | None) -> StageDefinition | None:
        return self._by_id.get(stage_id) if stage_id else None

    def index(self, stage_id: str) -> int:
        return next(i for i, s in enumerate(self.stages) if s.id == stage_id)

    @property
    def first(self) -> StageDefinition:
        return self.stages[0]

    def after(self, stage_id: str) -> StageDefinition | None:
        position = self.index(stage_id) + 1
        return self.stages[position] if position < len(self.stages) else None


def _problems(parsed: _StageFile) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for stage in parsed.stages:
        if stage.id in seen:
            problems.append(f"stage id {stage.id!r} is used twice")
        seen.add(stage.id)
        item_ids = [i.id for i in stage.checklist]
        for dup in sorted({i for i in item_ids if item_ids.count(i) > 1}):
            problems.append(f"stage {stage.id!r}: checklist item id {dup!r} is used twice")
        for rule in stage.artifacts:
            for status in rule.unknown_statuses():
                problems.append(
                    f"stage {stage.id!r}: {rule.kind} has no status {status!r}; "
                    f"use one of {sorted(MEMORY_STATUSES[rule.kind])}"
                )
    return problems


def load_stages(path: Path = STAGES_FILE) -> StageList:
    """Read and check the stage file. Raises StageConfigError with every problem found."""
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StageConfigError(f"Can't read the workflow stage file {path}: {exc}") from None
    except yaml.YAMLError as exc:
        raise StageConfigError(f"The workflow stage file {path} is not valid YAML: {exc}") from None
    try:
        parsed = _StageFile.model_validate(raw)
    except ValidationError as exc:
        lines = [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()]
        raise StageConfigError(
            f"The workflow stage file {path} is invalid:\n- " + "\n- ".join(lines)
        ) from None
    problems = _problems(parsed)
    if problems:
        raise StageConfigError(
            f"The workflow stage file {path} is invalid:\n- " + "\n- ".join(problems)
        )
    return StageList(parsed.stages)


@cache
def get_stages() -> StageList:
    """The stages from the default file, loaded once."""
    return load_stages()
