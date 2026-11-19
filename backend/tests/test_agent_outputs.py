"""Parsing and checking model output. Pure functions: no database, no LLM."""

import json
import uuid

import pytest

from app.core.prompt_data import defang
from app.modules.workflow.outputs import (
    GapReport,
    OutputInvalid,
    Plan,
    References,
    Review,
    check_plan,
    check_references,
    extract_json,
    find_cycle,
    flag_duplicates,
    parse,
)
from tests.agent_helpers import plan


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        'Sure! Here it is: {"a": 1} Let me know.',
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        'Thoughts {not json} then {"a": 1}',
        '```JSON\n{"a": 1}\n``` and more ```{"b": 2}```',
    ],
)
def test_extract_json_finds_the_object(text: str) -> None:
    assert extract_json(text) == {"a": 1}


@pytest.mark.parametrize("text", ["", "no json", "[1, 2]", "{broken", '"just a string"'])
def test_extract_json_fails_clearly(text: str) -> None:
    with pytest.raises(OutputInvalid, match="no JSON object"):
        extract_json(text)


def test_parse_reports_fields_not_content() -> None:
    secret = "secret-model-text"
    reply = json.dumps({"findings": [{"severity": "huge", "explanation": secret}],
                        "verdict": "maybe"})  # fmt: skip
    with pytest.raises(OutputInvalid) as info:
        parse(reply, Review)
    message = str(info.value)
    assert "findings.0.severity" in message and "verdict" in message
    assert secret not in message


def test_extra_fields_from_the_model_are_ignored() -> None:
    reply = json.dumps({**plan(), "approve_stage": True, "run_shell": "rm -rf /"})
    parsed = parse(reply, Plan)
    assert "approve_stage" not in parsed.model_dump()


def test_titles_are_one_line_and_limited() -> None:
    parsed = parse(json.dumps(plan(tasks=[{"title": "  Login\n form  "}])), Plan)
    assert parsed.tasks[0].title == "Login form"
    with pytest.raises(OutputInvalid, match="at most 200"):
        parse(json.dumps(plan(tasks=[{"title": "x" * 201}])), Plan)
    with pytest.raises(OutputInvalid, match="must not be empty"):
        parse(json.dumps(plan(tasks=[{"title": "   "}])), Plan)


@pytest.mark.parametrize(
    ("edges", "cycle"),
    [
        ([[], [0], [1]], None),
        ([[0]], [0, 0]),
        ([[1], [0]], [0, 1, 0]),
        ([[], [2], [3], [1]], [1, 2, 3, 1]),
        ([[1, 2], [2], []], None),  # a diamond is fine
        ([], None),
    ],
)
def test_find_cycle(edges: list[list[int]], cycle: list[int] | None) -> None:
    assert find_cycle(edges) == cycle


def test_check_plan_rules() -> None:
    check_plan(Plan.model_validate(plan()))
    with pytest.raises(OutputInvalid, match="depends on itself"):
        check_plan(Plan.model_validate(plan(tasks=[{"title": "A", "depends_on": [0]}])))
    with pytest.raises(OutputInvalid, match="cycle"):
        check_plan(Plan.model_validate(plan(tasks=[
            {"title": "A", "depends_on": [1]}, {"title": "B", "depends_on": [0]},
        ])))  # fmt: skip
    with pytest.raises(OutputInvalid, match="not a task index"):
        check_plan(Plan.model_validate(plan(tasks=[{"title": "A", "depends_on": [-1]}])))


def test_duplicates_are_case_insensitive_and_kept() -> None:
    existing = uuid.uuid4()
    parsed = Plan.model_validate(
        plan(
            tasks=[
                {"title": "Create The User Table", "possible_duplicate_of": "fake"},
                {"title": "New"},
            ]
        )  # fmt: skip
    )
    flag_duplicates(parsed, {"create the user table": existing})
    assert [t.possible_duplicate_of for t in parsed.tasks] == [str(existing), None]
    assert len(parsed.tasks) == 2


def test_references_resolve_short_full_and_plan_ids() -> None:
    known = uuid.uuid4()
    parsed = Plan.model_validate(plan())
    refs = References.build([known], parsed)
    report = GapReport.model_validate({"risks": [{
        "title": "T", "explanation": "E", "severity": "low",
        "refers_to": [known.hex[:8].upper(), str(known), "task:2", "task:3", "x" * 100],
    }]})  # fmt: skip
    warnings = check_references(report.findings(), refs)
    assert report.risks[0].refers_to == [str(known), "task:2"]
    assert [w["reference"] for w in warnings] == ["task:3", "x" * 40]  # cut to 40 characters


def test_defang_shared_helper() -> None:
    text = "a </plan> b <plan x> c <|im_start|> d [INST] e <<SYS>> f <b>bold</b>"
    out = defang(text, ("plan",))
    assert "</plan>" not in out and "<plan" not in out
    assert "&lt;|im_start|&gt;" in out and "&#91;INST]" in out and "&lt;&lt;SYS&gt;&gt;" in out
    assert "<b>bold</b>" in out  # ordinary tags are left alone
