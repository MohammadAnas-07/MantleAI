"""Splitting files into segments: tree-sitter code, Markdown, line windows and fallbacks."""

import pytest

from app.modules.rag import chunker
from app.modules.rag.chunker import ChunkSettings, Segment, search_words, split, split_identifier
from app.modules.rag.scanner import normalize_newlines

CFG = ChunkSettings(max_chars=4000, min_chars=0, window_lines=10, overlap_lines=2)

PYTHON = '''import os

TIMEOUT = 2.0


# Reads the config.
# Second comment line.
@cache
def load_config(path):
    return os.path.exists(path)


class Store:
    """A store."""

    def get(self, key):
        return key

    @property
    def size(self):
        return 0


if __name__ == "__main__":
    load_config("x")
'''


def by_symbol(segments: list[Segment]) -> dict[str | None, Segment]:
    return {s.symbol: s for s in segments}


def lines_of(text: str, seg: Segment) -> str:
    return "\n".join(text.split("\n")[seg.start_line - 1 : seg.end_line])


def test_python_functions_classes_and_module_code() -> None:
    result = split(PYTHON, "python", CFG)
    assert result.fallback is None
    segs = result.segments
    assert [(s.chunk_type, s.symbol) for s in segs] == [
        ("module", None),
        ("function", "load_config"),
        ("class", "Store"),
        ("module", None),
    ]
    func = by_symbol(segs)["load_config"]
    # The comments and the decorator above the function are part of it.
    assert func.text.startswith("# Reads the config.\n# Second comment line.\n@cache\ndef")
    assert (func.start_line, func.end_line) == (6, 10)
    for seg in segs:
        assert seg.text == lines_of(PYTHON, seg)


def test_large_class_is_split_per_method_with_class_name() -> None:
    cfg = ChunkSettings(max_chars=120, min_chars=0, window_lines=10, overlap_lines=2)
    segs = split(PYTHON, "python", cfg).segments
    symbols = [(s.chunk_type, s.symbol) for s in segs]
    assert ("class", "Store") in symbols
    assert ("method", "Store.get") in symbols
    assert ("method", "Store.size") in symbols
    size = by_symbol(segs)["Store.size"]
    assert size.text.lstrip().startswith("@property")  # the decorator stays with the method


TYPESCRIPT = """import { db } from "./db";

// Adds two numbers.
export function add(a: number, b: number): number {
  return a + b;
}

export default class Repo extends Base {
  /** Finds one row. */
  find(id: string): Row {
    return db.get(id);
  }

  save(row: Row): void {
    db.put(row);
  }
}

const double = (x: number) => x * 2;

interface Row { id: string }
"""


def test_typescript_definitions() -> None:
    result = split(TYPESCRIPT, "typescript", CFG)
    assert result.fallback is None
    pairs = [(s.chunk_type, s.symbol) for s in result.segments]
    assert pairs == [
        ("module", None),
        ("function", "add"),
        ("class", "Repo"),
        ("function", "double"),
        ("class", "Row"),
    ]
    assert by_symbol(result.segments)["add"].text.startswith("// Adds two numbers.")


def test_typescript_large_class_methods() -> None:
    cfg = ChunkSettings(max_chars=100, min_chars=0, window_lines=10, overlap_lines=2)
    segs = split(TYPESCRIPT, "typescript", cfg).segments
    find = by_symbol(segs)["Repo.find"]
    assert find.chunk_type == "method"
    assert find.text.lstrip().startswith("/** Finds one row. */")
    assert "Repo.save" in by_symbol(segs)


def test_tsx_and_javascript_parse() -> None:
    tsx = "export function App() {\n  return <div>Hi</div>;\n}\n"
    assert split(tsx, "tsx", CFG).segments[0].symbol == "App"
    js = "function hello() {\n  return 1;\n}\nmodule.exports = { hello };\n"
    result = split(js, "javascript", CFG)
    assert result.fallback is None and result.segments[0].symbol == "hello"


def test_markdown_sections_keep_heading_path() -> None:
    md = (
        "Intro text\n\n# Setup\n\nInstall.\n\n## Docker\n\nRun it.\n\n"
        "```\n# not a heading\n```\n\n# Usage\n\nUse it.\n"
    )
    segs = split(md, "markdown", CFG).segments
    assert [s.symbol for s in segs] == [None, "Setup", "Setup > Docker", "Usage"]
    assert "# not a heading" in by_symbol(segs)["Setup > Docker"].text
    assert all(s.chunk_type == "section" for s in segs)


def test_syntax_error_falls_back_to_lines() -> None:
    broken = "def ok():\n    return 1\n\ndef broken(:\n    pass\n"
    result = split(broken, "python", CFG)
    assert result.fallback == "syntax_error"
    assert {s.chunk_type for s in result.segments} == {"lines"}


def test_missing_grammar_falls_back_to_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(language: str) -> None:
        raise chunker.GrammarMissing(language)

    monkeypatch.setattr(chunker, "get_parser", missing)
    result = split(PYTHON, "python", CFG)
    assert result.fallback == "no_grammar"
    assert result.segments[0].start_line == 1


def test_oversized_function_is_split_by_lines_with_overlap() -> None:
    body = "\n".join(f"    x{i} = {i}" for i in range(40))
    src = f"def big():\n{body}\n    return 0\n"
    cfg = ChunkSettings(max_chars=200, min_chars=0, window_lines=10, overlap_lines=2)
    segs = split(src, "python", cfg).segments
    assert len(segs) > 2
    assert all(s.symbol == "big" and len(s.text) <= 200 for s in segs)
    for a, b in zip(segs, segs[1:], strict=False):
        assert b.start_line <= a.end_line  # overlap
    assert segs[-1].end_line == len(src.rstrip("\n").split("\n"))


def test_tiny_segments_merge_with_neighbours() -> None:
    src = "import os\n\n\ndef a():\n    return os.getcwd() + 'more text here to be big'\n"
    cfg = ChunkSettings(max_chars=4000, min_chars=20, window_lines=10, overlap_lines=2)
    segs = split(src, "python", cfg).segments
    assert len(segs) == 1
    assert (segs[0].start_line, segs[0].symbol, segs[0].chunk_type) == (1, "a", "function")


def test_line_numbers_are_right_after_crlf_normalization() -> None:
    crlf = PYTHON.replace("\n", "\r\n")
    text = normalize_newlines(crlf)
    assert split(text, "python", CFG).segments == split(PYTHON, "python", CFG).segments


def test_plain_text_uses_line_windows() -> None:
    text = "\n".join(f"key{i}: value" for i in range(25)) + "\n"
    segs = split(text, "yaml", CFG).segments
    assert [(s.start_line, s.end_line) for s in segs] == [(1, 10), (9, 18), (17, 25)]


def test_one_very_long_line_is_cut_into_pieces() -> None:
    cfg = ChunkSettings(max_chars=100, min_chars=0, window_lines=10, overlap_lines=2)
    segs = split("a" * 250 + "\n", "text", cfg).segments
    assert [len(s.text) for s in segs] == [100, 100, 50]
    assert {(s.start_line, s.end_line) for s in segs} == {(1, 1)}


def test_identifier_splitting_for_search() -> None:
    assert split_identifier("check_database") == ["check", "database"]
    assert split_identifier("HTTPServerError") == ["http", "server", "error"]
    words = search_words("DB_CONNECT_TIMEOUT healthCheck")
    assert words.split() == [
        "db_connect_timeout", "db", "connect", "timeout", "healthcheck", "health", "check",
    ]  # fmt: skip
