"""The evaluation script's question files, scoring and offline estimate. No keys, no network,
no database: the real run (which embeds) is only done by hand."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
CLICK = FIXTURES / "retrieval_questions_click.yaml"
# The public click repository at release 8.5.1; not in this repo (see the YAML header).
CLICK_REPO = Path(r"C:\Users\admin\Desktop\click-sample")


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "eval_retrieval", BACKEND / "scripts" / "eval_retrieval.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["eval_retrieval"] = module
    spec.loader.exec_module(module)
    return module


ev = load_script()


def test_the_sample_questions_still_load() -> None:
    questions = ev.load_questions(FIXTURES / "retrieval_questions.yaml")
    assert len(questions) == 20
    assert all(q.kind == "behaviour" and len(q.expected) == 1 for q in questions)


def test_the_click_questions_are_well_formed() -> None:
    questions = ev.load_questions(CLICK)
    assert len(questions) == 25
    kinds = {kind: sum(q.kind == kind for q in questions) for kind in ev.KINDS}
    assert all(n >= 5 for n in kinds.values()), kinds
    assert all(len(q.expected) == 2 for q in questions if q.kind == "two_files")
    assert all(f.startswith("src/click/") for q in questions for f in q.expected)
    assert len({q.question for q in questions}) == 25


@pytest.mark.skipif(not CLICK_REPO.is_dir(), reason="click-sample is not cloned on this machine")
def test_every_expected_click_file_exists() -> None:
    for q in ev.load_questions(CLICK):
        for path in q.expected:
            assert (CLICK_REPO / path).is_file(), (q.question, path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("[]", "non-empty list"),
        ("- question: x\n", "expected must be"),
        ("- question: x\n  expected: a.py\n  kind: other\n", "kind must be"),
        ("- question: x\n  expected: a.py\n  weight: 2\n", "unknown keys"),
        ("- expected: a.py\n", "missing question"),
    ],
)
def test_bad_question_files_are_refused(tmp_path: Path, body: str, message: str) -> None:
    path = tmp_path / "q.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        ev.load_questions(path)


def test_scoring_one_and_two_files() -> None:
    results = ["a.py", "b.py", "a.py", "c.py", "d.py", "e.py"]
    one = ev.score(results, ("c.py",))
    assert (one.recall, one.all_found, one.first_rank) == (1.0, True, 4)
    assert one.reciprocal_rank == pytest.approx(0.25)

    half = ev.score(results, ("b.py", "z.py"))
    assert (half.recall, half.all_found, half.first_rank) == (0.5, False, 2)

    both = ev.score(results, ("d.py", "a.py"))
    assert (both.recall, both.all_found, both.first_rank) == (1.0, True, 1)

    outside = ev.score(results, ("e.py",))  # rank 6: outside the top 5
    assert (outside.recall, outside.reciprocal_rank, outside.first_rank) == (0.0, 0.0, None)


def test_report_groups_by_kind() -> None:
    report = ev.Report()
    q_name = ev.Question("q1", ("a.py",), kind="name")
    q_two = ev.Question("q2", ("a.py", "b.py"), kind="two_files")
    for mode in ev.MODES:
        report.add(q_name, mode, ev.score(["a.py"], q_name.expected))
        report.add(q_two, mode, ev.score(["a.py"], q_two.expected))
    lines = report.lines()
    assert any(line.startswith("all questions (2)") for line in lines)
    assert any(line.strip().startswith("name (1)") for line in lines)
    two = next(line for line in lines if line.strip().startswith("two_files (1)"))
    assert "0.50  0.00 1.000" in two  # half the files, not all, first one at rank 1


def test_estimate_reads_the_folder_without_any_model_call() -> None:
    e = ev.estimate(FIXTURES / "sample_project")
    assert e["files"] == 16 and e["segments"] > 0 and e["tokens"] > 0
    assert e["model"] == "gemini/gemini-embedding-001"
    assert e["cost_usd"] > 0
