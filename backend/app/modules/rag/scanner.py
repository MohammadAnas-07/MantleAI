"""Walk a project folder and read its text files, skipping what must not be indexed.

Two steps, so unchanged files are never read again:
  1. `walk` lists candidate files by name and size: .gitignore rules (nested files and `!`
     negations), always-skipped folders and file types, sensitive names, symlinks, the size
     and file-count limits.
  2. `read_text` reads one file and checks its content: binary, encoding, secrets, empty,
     changed while reading.

Every skip has a reason code, collected in a `SkipReport`. Paths are stored relative to the
root, in POSIX form. Symlinks (and Windows junctions) are never followed, which also rules out
loops and links that leave the root. Nothing here logs file contents.
"""

import os
import stat as stat_module
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pathspec

from app.modules.rag.languages import language_for
from app.modules.rag.secret_scan import looks_like_secret, sensitive_spec

# Folders that are never entered, whatever .gitignore says.
SKIP_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "node_modules", "bower_components", "__pycache__", ".venv",
        "venv", "env", ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".cache",
        "dist", "build", "out", "target", ".next", ".nuxt", ".svelte-kit", ".parcel-cache",
        "coverage", "htmlcov", ".gradle", ".idea", ".vs", ".terraform", "site-packages",
    }
)  # fmt: skip

LOCK_FILES = frozenset(
    {
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock",
        "uv.lock", "Cargo.lock", "composer.lock", "Gemfile.lock", "go.sum", "bun.lockb",
        "requirements.lock",
    }
)  # fmt: skip

BINARY_SUFFIXES = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tif", ".tiff", ".psd",
        ".svgz", ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar",
        ".war", ".whl", ".egg", ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".lib",
        ".pyc", ".pyo", ".class", ".wasm", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3",
        ".mp4", ".wav", ".ogg", ".flac", ".mov", ".avi", ".mkv", ".webm", ".sqlite",
        ".sqlite3", ".db", ".parquet", ".npy", ".pkl", ".pickle", ".docx", ".xlsx", ".pptx",
        ".iso", ".dmg",
    }
)  # fmt: skip

MINIFIED_SUFFIXES = (".min.js", ".min.css", ".min.mjs", ".js.map", ".css.map", ".map")

# A line longer than this means generated or minified text.
MAX_LINE_CHARS = 10_000

_BOMS_UNSUPPORTED = (b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")
_UTF8_BOM = b"\xef\xbb\xbf"


class SkipReason:
    """Reason codes, stored in `documents.skip_reason` and the run's skip report."""

    IGNORED_DIR = "ignored_dir"
    GITIGNORED = "gitignored"
    SYMLINK = "symlink"
    SENSITIVE_NAME = "sensitive_name"
    POSSIBLE_SECRET = "possible secret"
    TOO_LARGE = "too_large"
    TOO_MANY_FILES = "too_many_files"
    TOO_MANY_SEGMENTS = "too_many_segments"
    LOCK_FILE = "lock_file"
    MINIFIED = "minified"
    BINARY = "binary"
    UNSUPPORTED_TYPE = "unsupported_type"
    UNSUPPORTED_ENCODING = "unsupported_encoding"
    EMPTY = "empty"
    LONG_LINES = "long_lines"
    UNREADABLE = "unreadable"
    CHANGED_WHILE_READING = "changed_while_reading"


# Reasons that are listed per file in the documents table. The others (ignored folders,
# .gitignore matches, symlinks) can number in the thousands and only appear in the report.
RECORDED_REASONS = frozenset(
    {
        SkipReason.SENSITIVE_NAME, SkipReason.POSSIBLE_SECRET, SkipReason.TOO_LARGE,
        SkipReason.TOO_MANY_FILES, SkipReason.TOO_MANY_SEGMENTS, SkipReason.LOCK_FILE,
        SkipReason.MINIFIED, SkipReason.BINARY, SkipReason.UNSUPPORTED_TYPE,
        SkipReason.UNSUPPORTED_ENCODING, SkipReason.EMPTY, SkipReason.LONG_LINES,
        SkipReason.UNREADABLE, SkipReason.CHANGED_WHILE_READING,
    }
)  # fmt: skip

REPORT_EXAMPLES = 5


@dataclass
class SkipReport:
    """Counts per reason, with the first few paths as examples."""

    counts: dict[str, int] = field(default_factory=dict)
    examples: dict[str, list[str]] = field(default_factory=dict)

    def add(self, reason: str, path: str) -> None:
        self.counts[reason] = self.counts.get(reason, 0) + 1
        examples = self.examples.setdefault(reason, [])
        if len(examples) < REPORT_EXAMPLES:
            examples.append(path)

    def as_dict(self) -> dict[str, dict[str, object]]:
        return {
            reason: {"count": self.counts[reason], "examples": self.examples[reason]}
            for reason in sorted(self.counts)
        }

    @property
    def total(self) -> int:
        return sum(self.counts.values())


@dataclass(frozen=True)
class FileEntry:
    path: str  # relative, POSIX
    abs_path: Path
    size: int
    mtime_ns: int
    language: str


@dataclass(frozen=True)
class SkippedFile:
    path: str
    reason: str
    size: int = 0


@dataclass
class WalkResult:
    files: list[FileEntry] = field(default_factory=list)
    skipped: list[SkippedFile] = field(default_factory=list)
    report: SkipReport = field(default_factory=SkipReport)

    def skip(self, path: str, reason: str, size: int = 0) -> None:
        self.skipped.append(SkippedFile(path, reason, size))
        self.report.add(reason, path)


@dataclass(frozen=True)
class WalkLimits:
    max_file_bytes: int
    max_files: int


def _is_link(entry: os.DirEntry[str]) -> bool:
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)  # Windows junctions, Python 3.12+
    return bool(is_junction and is_junction())


def _gitignore(directory: Path) -> pathspec.GitIgnoreSpec | None:
    path = directory / ".gitignore"
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return None
    return pathspec.GitIgnoreSpec.from_lines(lines)


def _ignored(specs: list[tuple[PurePosixPath, pathspec.GitIgnoreSpec]], rel: str) -> bool:
    """Git's rule: patterns from deeper .gitignore files win; inside one file the last
    matching pattern wins, and `!pattern` re-includes."""
    ignored = False
    trailing = "/" if rel.endswith("/") else ""
    for base, spec in specs:
        sub = rel if str(base) == "." else str(PurePosixPath(rel).relative_to(base)) + trailing
        result = spec.check_file(sub)
        if result.include is not None:
            ignored = result.include
    return ignored


def _file_skip_reason(name: str, rel: str, sensitive: pathspec.GitIgnoreSpec) -> str | None:
    lower = name.lower()
    if sensitive.match_file(rel):
        return SkipReason.SENSITIVE_NAME
    if name in LOCK_FILES or lower.endswith(".lock"):
        return SkipReason.LOCK_FILE
    if lower.endswith(MINIFIED_SUFFIXES):
        return SkipReason.MINIFIED
    if Path(lower).suffix in BINARY_SUFFIXES:
        return SkipReason.BINARY
    return None


def walk(root: Path, limits: WalkLimits) -> WalkResult:
    """List the files under `root` that may be indexed, in a stable (sorted) order."""
    result = WalkResult()
    sensitive = sensitive_spec()
    root_spec = _gitignore(root)
    specs = [(PurePosixPath("."), root_spec)] if root_spec else []
    _walk_dir(root, root, PurePosixPath("."), specs, sensitive, limits, result)
    return result


def _walk_dir(
    root: Path,
    directory: Path,
    rel_dir: PurePosixPath,
    specs: list[tuple[PurePosixPath, pathspec.GitIgnoreSpec]],
    sensitive: pathspec.GitIgnoreSpec,
    limits: WalkLimits,
    result: WalkResult,
) -> None:
    try:
        with os.scandir(directory) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError:
        result.skip(f"{rel_dir}/" if str(rel_dir) != "." else "./", SkipReason.UNREADABLE)
        return

    for entry in entries:
        rel = entry.name if str(rel_dir) == "." else f"{rel_dir}/{entry.name}"
        if _is_link(entry):
            result.skip(rel, SkipReason.SYMLINK)
            continue
        try:
            is_dir = entry.is_dir(follow_symlinks=False)
        except OSError:
            result.skip(rel, SkipReason.UNREADABLE)
            continue
        if is_dir:
            if entry.name in SKIP_DIRS or (Path(entry.path) / "pyvenv.cfg").exists():
                result.skip(f"{rel}/", SkipReason.IGNORED_DIR)
                continue
            if _ignored(specs, f"{rel}/"):
                result.skip(f"{rel}/", SkipReason.GITIGNORED)
                continue
            child = Path(entry.path)
            child_spec = _gitignore(child)
            child_specs = specs + [(PurePosixPath(rel), child_spec)] if child_spec else specs
            _walk_dir(root, child, PurePosixPath(rel), child_specs, sensitive, limits, result)
            continue

        if entry.name == ".gitignore":
            continue
        if _ignored(specs, rel):
            result.skip(rel, SkipReason.GITIGNORED)
            continue
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError:
            result.skip(rel, SkipReason.UNREADABLE)
            continue
        if not stat_module.S_ISREG(info.st_mode):
            continue  # sockets, devices, pipes
        reason = _file_skip_reason(entry.name, rel, sensitive)
        if reason is None:
            if language_for(rel) is None:
                reason = SkipReason.UNSUPPORTED_TYPE
            elif info.st_size > limits.max_file_bytes:
                reason = SkipReason.TOO_LARGE
            elif len(result.files) >= limits.max_files:
                reason = SkipReason.TOO_MANY_FILES
        if reason is not None:
            result.skip(rel, reason, info.st_size)
            continue
        result.files.append(
            FileEntry(rel, Path(entry.path), info.st_size, info.st_mtime_ns, language_for(rel))
        )


# ---- reading -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadResult:
    text: str | None  # normalized: no BOM, "\n" line endings
    skip_reason: str | None
    size: int
    mtime_ns: int


# Indirection so a test can simulate a file that changes while it is read.
_stat: Callable[[Path], os.stat_result] = os.stat


def read_text(path: Path, max_bytes: int) -> ReadResult:
    """Read one file as UTF-8 (with or without BOM) and check its content."""
    try:
        before = _stat(path)
        if before.st_size > max_bytes:
            return ReadResult(None, SkipReason.TOO_LARGE, before.st_size, before.st_mtime_ns)
        with open(path, "rb") as handle:
            data = handle.read(max_bytes + 1)
        after = _stat(path)
    except OSError:
        return ReadResult(None, SkipReason.UNREADABLE, 0, 0)

    def skip(reason: str) -> ReadResult:
        return ReadResult(None, reason, after.st_size, after.st_mtime_ns)

    if (
        before.st_mtime_ns != after.st_mtime_ns
        or before.st_size != after.st_size
        or len(data) != after.st_size
    ):
        return skip(SkipReason.CHANGED_WHILE_READING)
    if len(data) > max_bytes:
        return skip(SkipReason.TOO_LARGE)
    if data.startswith(_BOMS_UNSUPPORTED):
        return skip(SkipReason.UNSUPPORTED_ENCODING)
    if b"\x00" in data:
        return skip(SkipReason.BINARY)
    if data.startswith(_UTF8_BOM):
        data = data[len(_UTF8_BOM) :]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return skip(SkipReason.UNSUPPORTED_ENCODING)
    text = normalize_newlines(text)
    if not text.strip():
        return skip(SkipReason.EMPTY)
    if any(len(line) > MAX_LINE_CHARS for line in text.split("\n")):
        return skip(SkipReason.LONG_LINES)
    if looks_like_secret(text):
        return skip(SkipReason.POSSIBLE_SECRET)
    return ReadResult(text, None, after.st_size, after.st_mtime_ns)


def normalize_newlines(text: str) -> str:
    """CRLF and lone CR become LF, so hashes and line numbers don't depend on the OS."""
    return text.replace("\r\n", "\n").replace("\r", "\n")
