"""The evaluation questions are well formed and point at files that exist and get indexed."""

from pathlib import Path

import yaml

from app.modules.rag.scanner import WalkLimits, walk

FIXTURES = Path(__file__).parent / "fixtures"


def test_twenty_questions_with_existing_expected_files() -> None:
    questions = yaml.safe_load((FIXTURES / "retrieval_questions.yaml").read_text(encoding="utf-8"))
    assert len(questions) == 20
    indexed = {f.path for f in walk(FIXTURES / "sample_project", WalkLimits(10**6, 1000)).files}
    assert len(indexed) >= 15
    for item in questions:
        assert set(item) == {"question", "expected"}
        assert item["expected"] in indexed, item
