"""The facts collector on generated folders: no model, no network, no database.

It sees only what the index walk allowed (no .gitignore matches, sensitive names, links or
folders over the limits) and reads manifests through the same secret check as indexing.
"""

import json
from pathlib import Path
from typing import Any

from app.modules.rag.profile import MAX_DEPENDENCIES, MAX_LAYOUT, facts_for_folder
from app.modules.rag.scanner import WalkLimits
from tests.test_rag_scanner import link_dir, write

LIMITS = WalkLimits(max_file_bytes=1_000_000, max_files=5000)


def facts(root: Path, limits: WalkLimits = LIMITS) -> dict[str, Any]:
    return facts_for_folder(root, limits)


def names(items: list[dict[str, Any]], key: str = "name") -> list[str]:
    return [i[key] for i in items]


PYPROJECT = """
[project]
name = "demo"
dependencies = ["fastapi>=0.110", "SQLAlchemy[asyncio]~=2.0", "pydantic"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff"]

[project.scripts]
demo = "demo.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""


def python_repo(root: Path) -> None:
    write(root, "pyproject.toml", PYPROJECT)
    write(root, "app/main.py", "app = 1\n")
    write(root, "app/models.py", "x = 1\n")
    write(root, "tests/test_main.py", "def test_x():\n    pass\n")
    write(root, "alembic/env.py", "x = 1\n")
    write(root, "Dockerfile", "FROM python:3.12\n")
    write(root, "docker-compose.yml", "services: {}\n")
    write(root, ".github/workflows/ci.yml", "on: push\n")
    write(root, "Makefile", "test:\n\tpytest\nlint:\n\truff check .\n")


def test_a_python_repo(tmp_path: Path) -> None:
    python_repo(tmp_path)
    f = facts(tmp_path)
    assert f["languages"]["python"] == 4
    deps = {d["name"]: d for d in f["dependencies"]}
    assert set(deps) == {"fastapi", "sqlalchemy", "pydantic", "pytest", "ruff"}
    assert deps["pytest"]["dev"] is True and deps["fastapi"]["dev"] is False
    assert {d["source"] for d in deps.values()} == {"pyproject.toml"}
    assert names(f["frameworks"]) == ["FastAPI", "Pydantic", "pytest", "SQLAlchemy"]
    assert {m["name"]: m["source"] for m in f["markers"]} == {
        "ci_workflows": ".github/workflows/ci.yml",
        "compose": "docker-compose.yml",
        "dockerfile": "Dockerfile",
        "migrations": "alembic/env.py",
        "tests": "tests/test_main.py",
    }
    commands = {c["name"]: c for c in f["commands"]}
    assert commands["demo"] == {"name": "demo", "command": "demo.cli:main",
                                "source": "pyproject.toml", "kind": "script"}  # fmt: skip
    assert commands["make test"]["source"] == "Makefile"
    assert commands["pytest"]["kind"] == "inferred"
    assert {"path": "app/main.py", "kind": "python"} in [
        {"path": e["source"], "kind": e["kind"]} for e in f["entry_points"]
    ]
    assert {"kind": "pyproject", "source": "pyproject.toml"} in f["manifests"]


def test_a_node_repo(tmp_path: Path) -> None:
    write(tmp_path, "package.json", json.dumps({
        "name": "web", "scripts": {"dev": "vite", "build": "tsc -b && vite build",
                                   "test": "vitest run"},
        "dependencies": {"react": "^19.0.0", "@tanstack/react-query": "^5"},
        "devDependencies": {"vite": "^7", "vitest": "^3", "typescript": "~5.9"},
    }))  # fmt: skip
    write(tmp_path, "package-lock.json", "{}")
    write(tmp_path, "src/main.tsx", "export {}\n")
    write(tmp_path, "src/App.test.tsx", "export {}\n")
    f = facts(tmp_path)
    assert f["languages"]["tsx"] == 2
    assert names(f["frameworks"]) == ["React", "TypeScript", "Vite", "Vitest"]
    assert [(c["name"], c["command"]) for c in f["commands"]] == [
        ("npm run build", "tsc -b && vite build"), ("npm run dev", "vite"),
        ("npm run test", "vitest run"),
    ]  # fmt: skip
    assert {"kind": "lock_file", "source": "package-lock.json"} in f["manifests"]
    assert {m["name"] for m in f["markers"]} == {"tests"}
    assert names(f["entry_points"], "source") == ["src/main.tsx"]


def test_a_mixed_repo_with_requirements_files(tmp_path: Path) -> None:
    write(tmp_path, "backend/pyproject.toml", PYPROJECT)
    write(tmp_path, "backend/requirements.txt", "\n".join([
        "# pinned", "Django==5.1  # web", "-r base.txt", "-e ./local", "--index-url https://x",
        "git+https://example.com/x.git", "celery[redis]>=5", "", "requests ; python_version>'3'",
    ]))  # fmt: skip
    write(tmp_path, "frontend/package.json", json.dumps({"dependencies": {"vue": "3"}}))
    f = facts(tmp_path)
    by_source = {(d["name"], d["source"]) for d in f["dependencies"]}
    assert ("django", "backend/requirements.txt") in by_source
    assert ("celery", "backend/requirements.txt") in by_source
    assert ("requests", "backend/requirements.txt") in by_source
    assert ("vue", "frontend/package.json") in by_source
    assert not any("http" in d["name"] or d["name"].startswith("-") for d in f["dependencies"])
    assert {"Django", "Vue", "FastAPI"} <= set(names(f["frameworks"]))
    assert [x["path"] for x in f["layout"]] == ["backend", "frontend"]


def test_an_empty_folder(tmp_path: Path) -> None:
    f = facts(tmp_path)
    assert f["languages"] == {}
    assert all(f[k] == [] for k in f if k != "languages")


def test_huge_lists_are_capped(tmp_path: Path) -> None:
    deps = {f"pkg-{i:04}": "1" for i in range(MAX_DEPENDENCIES + 100)}
    write(tmp_path, "package.json", json.dumps({"dependencies": deps}))
    for i in range(MAX_LAYOUT + 30):
        write(tmp_path, f"dir{i:03}/a.py")
    f = facts(tmp_path)
    assert len(f["dependencies"]) == MAX_DEPENDENCIES
    assert len(f["layout"]) == MAX_LAYOUT


def test_a_deep_tree_and_deep_manifests(tmp_path: Path) -> None:
    folder = tmp_path
    for i in range(12):
        folder = folder / f"d{i}"
    write(folder, "package.json", json.dumps({"dependencies": {"express": "4"}}))
    write(tmp_path, "a/b/c/d/package.json", json.dumps({"dependencies": {"koa": "2"}}))
    f = facts(tmp_path, WalkLimits(10**6, 5000, max_depth=8))
    assert f["dependencies"] == []  # manifests deeper than three folders are not read
    assert all(len(x["path"].split("/")) <= 2 for x in f["layout"])


def test_fixture_and_example_manifests_are_not_the_project(tmp_path: Path) -> None:
    write(tmp_path, "tests/fixtures/app/package.json", json.dumps({"dependencies": {"x": "1"}}))
    write(tmp_path, "examples/package.json", json.dumps({"dependencies": {"y": "1"}}))
    assert facts(tmp_path)["dependencies"] == []


def test_a_link_loop_does_not_repeat_anything(tmp_path: Path) -> None:
    python_repo(tmp_path)
    link_dir(tmp_path / "app" / "loop", tmp_path)
    f = facts(tmp_path)
    assert f["languages"]["python"] == 4
    assert len(f["dependencies"]) == 5


SECRET = "sk-proj-" + "A1b2C3d4E5f6G7h8I9j0" * 3


def test_env_and_key_files_and_secret_manifests_are_left_out(tmp_path: Path) -> None:
    write(tmp_path, ".env", f"OPENAI_API_KEY={SECRET}\n")
    write(tmp_path, ".env.production", f"TOKEN={SECRET}\n")
    write(tmp_path, "id_rsa", "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n")
    write(tmp_path, "deploy/key.pem", "-----BEGIN PRIVATE KEY-----\nabc\n")
    write(tmp_path, "package.json", json.dumps({
        "scripts": {"deploy": f"curl -H 'Authorization: Bearer {SECRET}' https://x"},
        "dependencies": {"react": "19"},
    }))  # fmt: skip
    write(tmp_path, "app/main.py", "x = 1\n")
    f = facts(tmp_path)
    text = json.dumps(f)
    assert SECRET not in text and "BEGIN" not in text
    assert ".env" not in text and "id_rsa" not in text and "key.pem" not in text
    assert f["commands"] == [] and f["dependencies"] == []  # the whole manifest is skipped


def test_broken_manifests_are_skipped(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "[project\nname = ")
    write(tmp_path, "package.json", "{not json")
    write(tmp_path, "frontend/package.json", json.dumps(["a", "list"]))
    write(tmp_path, "app.py", "x = 1\n")
    f = facts(tmp_path)
    assert f["dependencies"] == [] and f["commands"] == []
    assert names(f["entry_points"], "source") == ["app.py"]


def test_gitignored_folders_are_not_facts(tmp_path: Path) -> None:
    write(tmp_path, ".gitignore", "private/\n")
    write(tmp_path, "private/package.json", json.dumps({"dependencies": {"secret-lib": "1"}}))
    write(tmp_path, "private/main.py", "x = 1\n")
    write(tmp_path, "src/index.ts", "export {}\n")
    f = facts(tmp_path)
    assert "private" not in json.dumps(f)


def test_the_same_folder_gives_the_same_facts(tmp_path: Path) -> None:
    python_repo(tmp_path)
    assert facts(tmp_path) == facts(tmp_path)


def test_manifests_with_odd_shapes_do_not_crash(tmp_path: Path) -> None:
    write(tmp_path, "pyproject.toml", "\n".join([
        'project = "not a table"', "dependency-groups = [1, 2]", "[tool]", 'poetry = "x"',
    ]))  # fmt: skip
    write(tmp_path, "a/pyproject.toml", "\n".join([
        "[project]", "dependencies = 3", "optional-dependencies = [1]", "scripts = [1]",
        "[tool.poetry]", 'dependencies = "x"', 'group = ["y"]',
    ]))  # fmt: skip
    write(tmp_path, "b/package.json", json.dumps({"dependencies": ["a"], "scripts": "x"}))
    f = facts(tmp_path)
    assert f["dependencies"] == [] and f["commands"] == []
