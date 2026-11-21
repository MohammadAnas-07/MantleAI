"""Project profile facts, collected from files without a model and without the network.

The input is what one index walk allowed: files that passed .gitignore, the sensitive-name
rules, the link rule and the depth and entry limits. Only a few manifests are read
(pyproject.toml, requirements*.txt, package.json, Makefile), through the same reader as
indexing, so a manifest that looks like it holds a secret is skipped whole. Every fact keeps
the path of the file it came from. Lists are capped and sorted, so the same folder always
gives the same facts.

Everything here is repository text: untrusted. It is stored as data and defanged where a
prompt uses it (conversations/context_builder.py). Nothing here logs.
"""

import json
import re
import tomllib
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from app.modules.rag.scanner import FileEntry, SkipReason, WalkLimits, read_text, walk
from app.modules.rag.secret_scan import looks_like_secret

MAX_DEPENDENCIES = 200
MAX_COMMANDS = 30
MAX_LAYOUT = 40
MAX_ENTRY_POINTS = 15
MAX_LANGUAGES = 15
MAX_COMMAND_CHARS = 200
MAX_NAME_CHARS = 100
# Manifests deeper than this many folders (backend/app/x/package.json) are not read: they are
# usually vendored or examples, not the project.
MANIFEST_MAX_FOLDERS = 3
MANIFEST_MAX_BYTES = 256_000
# Folders whose manifests describe something else (test data, samples, docs).
_NOT_THE_PROJECT = frozenset(
    {"test", "tests", "__tests__", "fixtures", "fixture", "examples", "example", "samples",
     "sample", "docs", "testdata"}
)  # fmt: skip

FRAMEWORKS = {
    "python": {
        "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "sqlalchemy": "SQLAlchemy",
        "pydantic": "Pydantic", "pytest": "pytest", "celery": "Celery", "langgraph": "LangGraph",
        "litellm": "LiteLLM", "alembic": "Alembic", "streamlit": "Streamlit",
    },
    "node": {
        "react": "React", "next": "Next.js", "vue": "Vue", "nuxt": "Nuxt", "svelte": "Svelte",
        "@sveltejs/kit": "SvelteKit", "@angular/core": "Angular", "vite": "Vite",
        "vitest": "Vitest", "jest": "Jest", "express": "Express", "@nestjs/core": "NestJS",
        "typescript": "TypeScript", "tailwindcss": "Tailwind CSS", "electron": "Electron",
    },
}  # fmt: skip

_ENTRY_NAMES = frozenset(
    {"main.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "__main__.py", "server.py",
     "cli.py", "main.ts", "main.tsx", "main.js", "index.ts", "index.tsx", "index.js",
     "server.ts", "server.js", "app.ts", "app.js"}
)  # fmt: skip
_COMPOSE = frozenset({"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"})
_CI_FILES = frozenset({".gitlab-ci.yml", "azure-pipelines.yml", ".travis.yml"})
_TEST_DIRS = frozenset({"tests", "test", "__tests__"})
_TEST_FILE = re.compile(r"^(test_.+\.py|.+_test\.py|.+\.(test|spec)\.[cm]?[jt]sx?)$")

_PY_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_NODE_NAME = re.compile(r"^(@[a-z0-9._-]+/)?[a-z0-9._-]+$", re.IGNORECASE)
_MAKE_TARGET = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:(?!=)")

Reader = Callable[[FileEntry], str | None]


def _parts(path: str) -> tuple[str, ...]:
    return PurePosixPath(path).parts


def _is_project_manifest(path: str) -> bool:
    folders = _parts(path)[:-1]
    return len(folders) <= MANIFEST_MAX_FOLDERS and not any(
        p.lower() in _NOT_THE_PROJECT for p in folders
    )


def _python_name(spec: str) -> str | None:
    """`SQLAlchemy[asyncio]~=2.0` -> `sqlalchemy` (PEP 503 form)."""
    match = _PY_NAME.match(spec)
    if not match:
        return None
    name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
    return name if len(name) <= MAX_NAME_CHARS else None


def _dep(name: str, ecosystem: str, dev: bool, source: str) -> dict[str, Any]:
    return {"name": name, "ecosystem": ecosystem, "dev": dev, "source": source}


# ---- manifests -------------------------------------------------------------------------------


def _table(value: object) -> dict[str, Any]:
    """A TOML table, or empty when the file has something else there."""
    return value if isinstance(value, dict) else {}


def _pyproject(text: str, source: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Dependencies, script commands, and whether pytest is configured."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return [], [], False
    deps: list[dict[str, Any]] = []
    project = _table(data.get("project"))
    tool = _table(data.get("tool"))
    poetry = _table(tool.get("poetry"))

    def add(specs: object, dev: bool) -> None:
        if isinstance(specs, list):
            for spec in specs:
                name = _python_name(spec) if isinstance(spec, str) else None
                if name:
                    deps.append(_dep(name, "python", dev, source))

    add(project.get("dependencies"), False)
    for group in _table(project.get("optional-dependencies")).values():
        add(group, True)
    for group in _table(data.get("dependency-groups")).values():
        add(group, True)
    add([n for n in _table(poetry.get("dependencies")) if n.lower() != "python"], False)
    for group in _table(poetry.get("group")).values():
        add(list(_table(_table(group).get("dependencies"))), True)
    commands = [
        {"name": name, "command": target, "source": source, "kind": "script"}
        for name, target in _table(project.get("scripts")).items()
        if isinstance(target, str)
    ]
    return deps, commands, isinstance(tool.get("pytest"), dict)


def _requirements(text: str, source: str) -> list[dict[str, Any]]:
    deps = []
    for raw in text.split("\n"):
        line = re.split(r"(^|\s)#", raw, maxsplit=1)[0].strip()
        if not line or line.startswith("-") or "://" in line or line.startswith("git+"):
            continue
        name = _python_name(line)
        if name:
            deps.append(_dep(name, "python", False, source))
    return deps


def _package_json(text: str, source: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    try:
        data = json.loads(text)
    except ValueError:
        return [], []
    if not isinstance(data, dict):
        return [], []
    deps = []
    for key, dev in (("dependencies", False), ("devDependencies", True)):
        table = data.get(key)
        if isinstance(table, dict):
            deps += [
                _dep(name, "node", dev, source)
                for name in table
                if isinstance(name, str) and len(name) <= MAX_NAME_CHARS and _NODE_NAME.match(name)
            ]
    scripts = data.get("scripts")
    commands = []
    if isinstance(scripts, dict):
        commands = [
            {"name": f"npm run {name}", "command": command, "source": source, "kind": "script"}
            for name, command in scripts.items()
            if isinstance(name, str) and isinstance(command, str) and len(name) <= MAX_NAME_CHARS
        ]
    return deps, commands


def _makefile(text: str, source: str) -> list[dict[str, Any]]:
    targets = []
    for line in text.split("\n"):
        match = _MAKE_TARGET.match(line)
        if match and not match.group(1).startswith("."):
            target = match.group(1)
            targets.append({"name": f"make {target}", "command": f"make {target}",
                            "source": source, "kind": "make"})  # fmt: skip
    return targets


# ---- the collector ---------------------------------------------------------------------------


def _first(paths: Iterable[str]) -> str | None:
    return min(paths, default=None)


def _markers(paths: Sequence[str]) -> list[dict[str, Any]]:
    def named(test: Callable[[str], bool]) -> str | None:
        return _first(p for p in paths if test(p))

    def name_of(path: str) -> str:
        return PurePosixPath(path).name.lower()

    found = {
        "dockerfile": named(lambda p: name_of(p).startswith("dockerfile")
                            or name_of(p).endswith(".dockerfile")),
        "compose": named(lambda p: name_of(p) in _COMPOSE),
        "migrations": named(lambda p: any(x.lower() in {"migrations", "alembic"}
                                          for x in _parts(p)[:-1])),
        "ci_workflows": named(lambda p: p.startswith(".github/workflows/")
                              or name_of(p) in _CI_FILES),
        "tests": named(lambda p: any(x.lower() in _TEST_DIRS for x in _parts(p)[:-1])
                       or bool(_TEST_FILE.match(name_of(p)))),
    }  # fmt: skip
    return [{"name": k, "source": v} for k, v in sorted(found.items()) if v]


def _layout(paths: Sequence[str]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for path in paths:
        folders = _parts(path)[:-1]
        for depth in (1, 2):
            if len(folders) >= depth:
                counts["/".join(folders[:depth])] += 1
    return [{"path": p, "files": n} for p, n in sorted(counts.items())][:MAX_LAYOUT]


def _entry_points(files: Sequence[FileEntry]) -> list[dict[str, Any]]:
    found = [
        {"source": f.path, "kind": f.language}
        for f in files
        if PurePosixPath(f.path).name.lower() in _ENTRY_NAMES and _is_project_manifest(f.path)
    ]
    return sorted(found, key=lambda e: (len(_parts(e["source"])), e["source"]))[:MAX_ENTRY_POINTS]


def _frameworks(deps: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    found: dict[str, str] = {}
    for dep in sorted(deps, key=lambda d: (d["source"], d["name"])):
        name = FRAMEWORKS[dep["ecosystem"]].get(dep["name"].lower())
        if name and name not in found:
            found[name] = dep["source"]
    return [{"name": n, "source": s} for n, s in sorted(found.items(), key=lambda x: x[0].lower())]


def _safe_command(command: dict[str, Any]) -> dict[str, Any] | None:
    text = command["command"]
    if looks_like_secret(text, "command"):
        return None
    return command | {"command": text[:MAX_COMMAND_CHARS]}


def collect_facts(
    files: Sequence[FileEntry], lock_paths: Sequence[str], read: Reader
) -> dict[str, Any]:
    """The facts for one project. `files` are the files the index walk kept (and the run did
    not skip for content), `lock_paths` the lock files it saw by name, and `read` returns a
    file's text, or None when it must not be used (a secret, too large, unreadable)."""
    files = sorted(files, key=lambda f: f.path)
    paths = [f.path for f in files]
    deps: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    pytest_source: str | None = None

    for entry in files:
        name = PurePosixPath(entry.path).name.lower()
        kind = (
            "pyproject" if name == "pyproject.toml"
            else "requirements" if name.startswith("requirements") and name.endswith(".txt")
            else "package_json" if name == "package.json"
            else "makefile" if name == "makefile"
            else None
        )  # fmt: skip
        if kind is None or not _is_project_manifest(entry.path):
            continue
        text = read(entry)
        if text is None:
            continue
        manifests.append({"kind": kind, "source": entry.path})
        if kind == "pyproject":
            found, scripts, pytest_configured = _pyproject(text, entry.path)
            deps += found
            commands += scripts
            if pytest_configured and pytest_source is None:
                pytest_source = entry.path
        elif kind == "requirements":
            deps += _requirements(text, entry.path)
        elif kind == "package_json":
            found, scripts = _package_json(text, entry.path)
            deps += found
            commands += scripts
        else:
            commands += _makefile(text, entry.path)

    manifests += [
        {"kind": "lock_file", "source": p} for p in sorted(lock_paths) if _is_project_manifest(p)
    ]
    unique = {(d["source"], d["name"]): d for d in deps}
    deps = [unique[k] for k in sorted(unique)][:MAX_DEPENDENCIES]
    if pytest_source is None:
        pytest_source = next((d["source"] for d in deps if d["name"] == "pytest"), None)
    if pytest_source is not None:
        commands.append({"name": "pytest", "command": "pytest", "source": pytest_source,
                         "kind": "inferred"})  # fmt: skip
    safe = [c for c in (_safe_command(c) for c in commands) if c is not None]
    seen_names: set[str] = set()
    commands = []
    for command in sorted(safe, key=lambda c: (c["name"], c["source"])):
        if command["name"] not in seen_names:
            seen_names.add(command["name"])
            commands.append(command)

    languages = Counter(f.language for f in files)
    return {
        "languages": dict(sorted(languages.most_common(MAX_LANGUAGES))),
        "dependencies": deps,
        "markers": _markers(paths),
        "manifests": sorted(manifests, key=lambda m: (m["source"], m["kind"])),
        "frameworks": _frameworks(deps),
        "commands": commands[:MAX_COMMANDS],
        "layout": _layout(paths),
        "entry_points": _entry_points(files),
    }


def lock_paths_of(skipped: Iterable[Any]) -> list[str]:
    return [s.path for s in skipped if s.reason == SkipReason.LOCK_FILE]


def read_manifest(entry: FileEntry, max_file_bytes: int) -> str | None:
    """A manifest's text, or None: the same secret, size and encoding checks as indexing."""
    return read_text(entry.abs_path, min(max_file_bytes, MANIFEST_MAX_BYTES)).text


def facts_for_folder(root: Path, limits: WalkLimits) -> dict[str, Any]:
    """Walk `root` and collect its facts. For tests and scripts; an index run uses the walk it
    already made (indexer.py)."""
    walked = walk(root, limits)
    return collect_facts(
        walked.files,
        lock_paths_of(walked.skipped),
        lambda entry: read_manifest(entry, limits.max_file_bytes),
    )
