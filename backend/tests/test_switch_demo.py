"""Offline checks for scripts/switch_demo.py (the script itself needs real keys)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "switch_demo.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("switch_demo", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_data_file_has_five_decisions_and_five_questions() -> None:
    data = yaml.safe_load(SCRIPT.with_suffix(".yaml").read_text(encoding="utf-8"))
    decisions = [t for t in data["turns"] if t.startswith("Decision") or "Decision 1" in t]
    assert len(decisions) == 5
    assert len(data["questions"]) == 5
    for q in data["questions"]:
        assert q["expect_all"] or q["expect_any"]


def test_scoring() -> None:
    score = load().score
    assert score("We chose PostgreSQL for full-text search.", ["postgres"], ["full-text"]) == (
        True,
        [],
    )
    passed, missing = score("We chose MySQL.", ["postgres"], ["full-text", "jsonb"])
    assert not passed and missing == ["postgres", "one of: full-text, jsonb"]
    assert score("Magic-Link login", [], ["magic link", "magic-link"])[0] is True
