"""The stage file is checked at startup and a bad one fails with a clear message. No database."""

from pathlib import Path

import pytest

from app.modules.workflow.stages import STAGES_FILE, StageConfigError, load_stages

GOOD_STAGE = """
  - id: {id}
    title: T
    goal: G
    checklist:
      - {{id: a, text: A, required: true}}
    artifacts:
      - {{type: min_memory_items, kind: task, min: 1, text: one task}}
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "stages.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_shipped_file_has_the_five_stages_in_order() -> None:
    stages = load_stages(STAGES_FILE)
    assert [s.id for s in stages.stages] == [
        "requirements", "architecture", "technical_decisions", "task_breakdown",
        "implementation_plan",
    ]  # fmt: skip
    assert all(s.checklist for s in stages.stages)
    assert stages.after("implementation_plan") is None
    assert stages.after("requirements").id == "architecture"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("stages:" + GOOD_STAGE.format(id="a") + GOOD_STAGE.format(id="a"), "'a' is used twice"),
        ("stages:\n  - {id: a, title: T, goal: G, checklist: []}", "checklist"),
        (
            "stages:\n  - id: a\n    title: T\n    goal: G\n    checklist: [{id: x, text: X, "
            "required: true}]\n    artifacts: [{type: magic, kind: task, min: 1, text: t}]",
            "type",
        ),
        (
            "stages:\n  - id: a\n    title: T\n    goal: G\n    checklist: [{id: x, text: X, "
            "required: true}]\n    artifacts: [{type: min_memory_items, kind: wish, min: 1, "
            "text: t}]",
            "unknown memory kind",
        ),
        (
            "stages:\n  - id: a\n    title: T\n    goal: G\n    checklist: [{id: x, text: X, "
            "required: true}]\n    artifacts: [{type: min_memory_items, kind: task, "
            "statuses: [finished], min: 1, text: t}]",
            "task has no status 'finished'",
        ),
        (
            "stages:\n  - id: a\n    title: T\n    goal: G\n    checklist:\n"
            "      - {id: x, text: X, required: true}\n      - {id: x, text: Y, required: false}",
            "checklist item id 'x' is used twice",
        ),
        ("stages: []", "stages"),
        ("stages: [", "not valid YAML"),
        ("stages:\n  - {id: a, title: T, goal: G, checklist: [{id: x, text: X}]}", "required"),
    ],
)
def test_invalid_files_fail_with_a_clear_message(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(StageConfigError) as info:
        load_stages(write(tmp_path, text))
    assert message in str(info.value)
    assert "stages.yaml" in str(info.value)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(StageConfigError, match="Can't read"):
        load_stages(tmp_path / "nope.yaml")


async def test_app_start_checks_the_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.main import app, lifespan
    from app.modules.workflow import stages

    bad = write(tmp_path, "stages: []")
    stages.get_stages.cache_clear()
    monkeypatch.setattr(stages, "STAGES_FILE", bad)
    monkeypatch.setattr(stages.load_stages, "__defaults__", (bad,))
    try:
        with pytest.raises(StageConfigError):
            async with lifespan(app):
                pass
    finally:
        stages.get_stages.cache_clear()
