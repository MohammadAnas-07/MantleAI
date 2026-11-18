"""Which files are indexed, and as which language. Decided by file name only."""

from pathlib import PurePosixPath

# Languages split by syntax (tree-sitter grammar names).
CODE_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",  # the JavaScript grammar parses JSX
}

MARKDOWN = {".md": "markdown", ".markdown": "markdown", ".mdx": "markdown"}

# Other text files, split by lines.
TEXT_LANGUAGES = {
    ".json": "json", ".jsonc": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".ini": "ini", ".cfg": "ini", ".conf": "ini", ".sql": "sql", ".html": "html",
    ".htm": "html", ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    ".vue": "vue", ".svelte": "svelte", ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".ps1": "powershell", ".psm1": "powershell", ".bat": "batch", ".cmd": "batch",
    ".txt": "text", ".rst": "rst", ".xml": "xml", ".graphql": "graphql",
    ".gql": "graphql", ".proto": "protobuf", ".go": "go", ".rs": "rust", ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin", ".swift": "swift", ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".hpp": "cpp", ".cs": "csharp", ".rb": "ruby",
    ".php": "php", ".lua": "lua", ".r": "r", ".scala": "scala", ".dart": "dart",
    ".ex": "elixir", ".exs": "elixir", ".tf": "terraform", ".dockerfile": "dockerfile",
    ".csv": "csv", ".ipynb": "json", ".mako": "text",
}  # fmt: skip

# Files known by their full name.
TEXT_NAMES = {
    "dockerfile": "dockerfile", "makefile": "make", "justfile": "make", "procfile": "text",
    "readme": "text", "license": "text", "changelog": "text", ".editorconfig": "ini",
    ".gitattributes": "text", ".dockerignore": "text", "alembic.ini": "ini",
}  # fmt: skip


def language_for(path: str) -> str | None:
    """The language of a file, or None when it is not a supported text type."""
    name = PurePosixPath(path).name.lower()
    suffix = PurePosixPath(name).suffix
    for table in (CODE_LANGUAGES, MARKDOWN, TEXT_LANGUAGES):
        if suffix in table:
            return table[suffix]
    if name in TEXT_NAMES:
        return TEXT_NAMES[name]
    if name.startswith("dockerfile"):
        return "dockerfile"
    return None
