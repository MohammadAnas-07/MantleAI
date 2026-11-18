"""Module imports follow the allowed directions (docs/architecture.md, ADR 0006).

A module may import another module only if the table below allows it, and only that module's
`service.py` (rule 6). `app/api` sits above the modules and may use any module's service;
`app/db/models.py` imports every table for Alembic and is not a module.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
MODULES = APP / "modules"

# Who may call whom ("May call" column of docs/architecture.md, amended by ADR 0006).
ALLOWED: dict[str, set[str]] = {
    "projects": set(),
    "llm": set(),
    "rag": {"llm", "projects"},
    "conversations": {"projects", "rag", "llm"},
    "workflow": {"projects", "rag", "llm"},
    "teaching": {"projects", "conversations", "rag", "llm"},
    "execution": set(),
}


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
            names.extend(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def violations() -> list[str]:
    found: list[str] = []
    for module_dir in sorted(p for p in MODULES.iterdir() if p.is_dir()):
        owner = module_dir.name
        if owner.startswith("__"):
            continue
        for path in module_dir.rglob("*.py"):
            for name in imported_modules(path):
                parts = name.split(".")
                if parts[:2] != ["app", "modules"] or len(parts) < 3:
                    continue
                target = parts[2]
                if target == owner:
                    continue
                where = f"{path.relative_to(APP)} imports {name}"
                if target not in ALLOWED.get(owner, set()):
                    found.append(f"{where}: {owner} may not call {target}")
                elif len(parts) >= 4 and parts[3] != "service":
                    found.append(f"{where}: only {target}.service may be imported")
    return found


def test_modules_import_only_in_allowed_directions() -> None:
    assert violations() == []


def test_the_allowed_table_has_no_cycles() -> None:
    def reaches(start: str, goal: str, seen: set[str]) -> bool:
        for nxt in ALLOWED[start]:
            if nxt == goal or (nxt not in seen and reaches(nxt, goal, seen | {nxt})):
                return True
        return False

    assert [m for m in ALLOWED if reaches(m, m, {m})] == []


def test_the_checker_catches_a_bad_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tests.test_module_boundaries as checker

    fake_app = tmp_path / "app"
    (fake_app / "modules" / "projects").mkdir(parents=True)
    (fake_app / "modules" / "projects" / "x.py").write_text(
        "from app.modules.rag.models import Chunk\n"
    )
    (fake_app / "modules" / "rag").mkdir()
    (fake_app / "modules" / "rag" / "y.py").write_text("from app.modules.llm.gateway import G\n")
    monkeypatch.setattr(checker, "APP", fake_app)
    monkeypatch.setattr(checker, "MODULES", fake_app / "modules")
    found = checker.violations()
    assert any("projects may not call rag" in v for v in found)
    assert any("only llm.service may be imported" in v for v in found)
