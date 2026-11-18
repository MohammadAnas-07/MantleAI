"""Split a normalized text file into segments ("chunks" in the tables).

- Python, TypeScript, TSX and JavaScript: tree-sitter. One segment per top-level function or
  class. A class larger than the size limit is split per method; each method keeps the class
  name in its symbol (`Class.method`). Decorators and the comments right above a definition
  stay attached to it. Top-level code between definitions becomes `module` segments.
- Markdown: one segment per heading section; the symbol is the heading path ("Setup > Docker").
- Everything else, and code whose grammar is missing or that has syntax errors: line windows
  with overlap. The fallback reason is returned so the caller can record it.

A segment larger than `chunk_max_chars` is split by lines with overlap, and tiny segments are
merged into a neighbour. Line numbers are 1-based and inclusive, on the LF-normalized text.
Pure functions: no I/O, no logging.
"""

import re
from dataclasses import dataclass, replace
from functools import cache
from typing import Any

from app.core.config import settings

CODE_GRAMMARS = frozenset({"python", "typescript", "tsx", "javascript"})


@dataclass(frozen=True)
class ChunkSettings:
    max_chars: int
    min_chars: int
    window_lines: int
    overlap_lines: int

    @classmethod
    def from_settings(cls) -> "ChunkSettings":
        return cls(
            max_chars=settings.chunk_max_chars,
            min_chars=settings.chunk_min_chars,
            window_lines=settings.chunk_window_lines,
            overlap_lines=settings.chunk_overlap_lines,
        )


@dataclass(frozen=True)
class Segment:
    start_line: int
    end_line: int
    text: str
    chunk_type: str  # function | class | method | module | section | lines
    symbol: str | None


@dataclass(frozen=True)
class SplitResult:
    segments: list[Segment]
    fallback: str | None  # None, "syntax_error" or "no_grammar"


class GrammarMissing(Exception):
    pass


@cache
def _parser(language: str) -> Any:
    try:
        from tree_sitter_language_pack import get_parser

        return get_parser(language)  # type: ignore[arg-type]
    except Exception as exc:  # LookupError, ImportError, or a broken native library
        raise GrammarMissing(language) from exc


def get_parser(language: str) -> Any:
    """The tree-sitter parser for `language`; GrammarMissing if it can't be loaded."""
    return _parser(language)


# ---- public entry point --------------------------------------------------------------------


def split(text: str, language: str, cfg: ChunkSettings | None = None) -> SplitResult:
    """Split `text` (already LF-normalized) into segments."""
    cfg = cfg or ChunkSettings.from_settings()
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # a trailing newline is not an extra line
    fallback: str | None = None
    if language in CODE_GRAMMARS:
        try:
            ranges = _code_ranges(text, language, cfg)
        except GrammarMissing:
            ranges, fallback = None, "no_grammar"
        except _SyntaxError:
            ranges, fallback = None, "syntax_error"
    elif language == "markdown":
        ranges = _markdown_ranges(lines)
    else:
        ranges = None
    if ranges is None:
        ranges = [_Range(1, len(lines), "lines", None)]
    segments = _finish(lines, ranges, cfg)
    return SplitResult(segments, fallback)


# ---- ranges --------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Range:
    start: int  # 1-based, inclusive
    end: int
    chunk_type: str
    symbol: str | None


class _SyntaxError(Exception):
    pass


_PY_DEFS = {"function_definition": "function", "class_definition": "class"}
_JS_DEFS = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "class_declaration": "class",
    "abstract_class_declaration": "class",
    "interface_declaration": "class",
    "enum_declaration": "class",
    "type_alias_declaration": "class",
}
_JS_FUNCTION_VALUES = {"arrow_function", "function_expression", "function", "generator_function"}
_METHOD_NODES = {"function_definition", "decorated_definition", "method_definition"}


def _name(node: Any) -> str | None:
    name = node.child_by_field_name("name")
    return name.text.decode("utf-8", "replace") if name is not None else None


def _definition(node: Any, language: str) -> tuple[str, str | None, Any] | None:
    """(chunk type, symbol, definition node) for a top-level definition, else None."""
    if language == "python":
        inner = node
        if node.type == "decorated_definition":
            inner = node.child_by_field_name("definition")
        if inner is not None and inner.type in _PY_DEFS:
            return _PY_DEFS[inner.type], _name(inner), inner
        return None
    inner = node
    if node.type == "export_statement":
        inner = node.child_by_field_name("declaration")
        if inner is None:
            return None
    if inner.type in _JS_DEFS:
        return _JS_DEFS[inner.type], _name(inner), inner
    if inner.type in ("lexical_declaration", "variable_declaration"):
        for child in inner.named_children:
            if child.type == "variable_declarator":
                value = child.child_by_field_name("value")
                if value is not None and value.type in _JS_FUNCTION_VALUES:
                    return "function", _name(child), inner
    return None


def _class_body(definition: Any, language: str) -> Any:
    field = "body"
    body = definition.child_by_field_name(field)
    if body is None and language != "python":
        body = next((c for c in definition.named_children if c.type == "class_body"), None)
    return body


def _code_ranges(text: str, language: str, cfg: ChunkSettings) -> list[_Range]:
    tree = get_parser(language).parse(text.encode("utf-8"))
    root = tree.root_node
    if root.has_error:
        raise _SyntaxError
    ranges: list[_Range] = []
    module: list[tuple[int, int]] = []  # pending top-level code, as line spans
    comments: list[Any] = []  # comments waiting to attach to the next definition

    def flush_module() -> None:
        if module:
            ranges.append(_Range(module[0][0], module[-1][1], "module", None))
            module.clear()

    def flush_comments() -> None:
        for comment in comments:
            module.append((comment.start_point.row + 1, comment.end_point.row + 1))
        comments.clear()

    for node in root.children:
        start, end = node.start_point.row + 1, node.end_point.row + 1
        if node.type == "comment":
            if comments and start > comments[-1].end_point.row + 2:
                flush_comments()  # a blank line breaks the attachment
            comments.append(node)
            continue
        found = _definition(node, language)
        if found is None:
            flush_comments()
            module.append((start, end))
            continue
        kind, symbol, definition = found
        if comments and comments[-1].end_point.row + 2 >= start:
            start = comments[0].start_point.row + 1
            comments.clear()
        else:
            flush_comments()
        flush_module()
        size = len("\n".join(text.split("\n")[start - 1 : end]))
        if kind == "class" and size > cfg.max_chars:
            ranges.extend(_class_ranges(definition, language, symbol, start, end))
        else:
            ranges.append(_Range(start, end, kind, symbol))
    flush_comments()
    flush_module()
    return ranges


def _class_ranges(
    definition: Any, language: str, class_name: str | None, start: int, end: int
) -> list[_Range]:
    """A large class: the header (up to the first method) and one range per method."""
    body = _class_body(definition, language)
    members = [c for c in body.named_children if c.type in _METHOD_NODES] if body else []
    if not members:
        return [_Range(start, end, "class", class_name)]
    out: list[_Range] = []
    cursor = start
    for i, member in enumerate(members):
        m_start = member.start_point.row + 1
        # Comments and decorators directly above a method belong to it.
        prev = member.prev_named_sibling
        while prev is not None and prev.type in ("comment", "decorator"):
            if prev.end_point.row + 2 < m_start:
                break
            m_start = prev.start_point.row + 1
            prev = prev.prev_named_sibling
        m_start = max(m_start, cursor)
        if m_start > cursor:
            out.append(_Range(cursor, m_start - 1, "class", class_name))
        m_end = member.end_point.row + 1
        if i == len(members) - 1:
            m_end = max(m_end, end)  # closing brace and trailing members stay with the last
        inner = member
        if member.type == "decorated_definition":
            inner = member.child_by_field_name("definition")
        name = _name(inner) if inner is not None else None
        symbol = f"{class_name}.{name}" if class_name and name else name or class_name
        out.append(_Range(m_start, m_end, "method", symbol))
        cursor = m_end + 1
    return out


_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^ {0,3}(```|~~~)")


def _markdown_ranges(lines: list[str]) -> list[_Range]:
    """One range per heading section; text before the first heading is its own range."""
    starts: list[tuple[int, str | None]] = []
    path: list[tuple[int, str]] = []
    fence: str | None = None
    for number, line in enumerate(lines, start=1):
        fence_match = _FENCE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            fence = None if fence == marker else (fence or marker)
            continue
        if fence:
            continue
        heading = _HEADING.match(line)
        if heading:
            level, title = len(heading.group(1)), heading.group(2).strip()
            path = [(lv, t) for lv, t in path if lv < level] + [(level, title)]
            starts.append((number, " > ".join(t for _, t in path)))
    if not starts or starts[0][0] != 1:
        starts.insert(0, (1, None))
    ranges = []
    for i, (start, symbol) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else len(lines)
        if end >= start:
            ranges.append(_Range(start, end, "section", symbol))
    return ranges


# ---- sizing --------------------------------------------------------------------------------


def _text(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start - 1 : end])


def _windows(lines: list[str], rng: _Range, cfg: ChunkSettings) -> list[Segment]:
    """Split one range into line windows with overlap, each within `max_chars`. A single
    line longer than `max_chars` is cut into pieces that share its line number."""
    out: list[Segment] = []
    i = rng.start
    while i <= rng.end:
        j = min(i + cfg.window_lines - 1, rng.end)
        while j > i and len(_text(lines, i, j)) > cfg.max_chars:
            j -= 1
        text = _text(lines, i, j)
        if len(text) > cfg.max_chars:  # one very long line
            for k in range(0, len(text), cfg.max_chars):
                out.append(Segment(i, i, text[k : k + cfg.max_chars], rng.chunk_type, rng.symbol))
        else:
            out.append(Segment(i, j, text, rng.chunk_type, rng.symbol))
        if j >= rng.end:
            break
        i = max(j + 1 - cfg.overlap_lines, i + 1)
    return out


def _merge_tiny(segments: list[Segment], lines: list[str], cfg: ChunkSettings) -> list[Segment]:
    """Merge a segment smaller than `min_chars` into the next one (or into the previous one,
    for the last), when the result stays within `max_chars` and the two don't overlap."""
    out: list[Segment] = []
    pending: Segment | None = None
    for seg in segments:
        if pending is not None:
            merged = _join(pending, seg, lines, cfg)
            if merged is None:
                out.append(pending)
            else:
                seg = merged
            pending = None
        if len(seg.text.strip()) < cfg.min_chars:
            pending = seg
        else:
            out.append(seg)
    if pending is not None:
        merged = _join(out[-1], pending, lines, cfg) if out else None
        if merged is None:
            out.append(pending)
        else:
            out[-1] = merged
    return out


def _join(a: Segment, b: Segment, lines: list[str], cfg: ChunkSettings) -> Segment | None:
    if b.start_line <= a.end_line:
        return None  # overlapping windows, or pieces of one long line
    text = _text(lines, a.start_line, b.end_line)
    if len(text) > cfg.max_chars:
        return None
    # Keep the name of the definition, not of loose module code.
    main = a if b.chunk_type == "module" and a.chunk_type != "module" else b
    return replace(main, start_line=a.start_line, end_line=b.end_line, text=text)


def _finish(lines: list[str], ranges: list[_Range], cfg: ChunkSettings) -> list[Segment]:
    segments: list[Segment] = []
    for rng in ranges:
        text = _text(lines, rng.start, rng.end)
        if not text.strip():
            continue
        if len(text) <= cfg.max_chars and rng.chunk_type != "lines":
            segments.append(Segment(rng.start, rng.end, text, rng.chunk_type, rng.symbol))
        else:
            segments.extend(_windows(lines, rng, cfg))
    return _merge_tiny(segments, lines, cfg)


# ---- text for the embedder and for full-text search ----------------------------------------

_IDENT = re.compile(r"[A-Za-z0-9_]+")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def embedding_input(path: str, symbol: str | None, text: str) -> str:
    """What is sent to the embedding model: where the text is, what it is, then the text."""
    header = f"File: {path}" + (f"\nSymbol: {symbol}" if symbol else "")
    return f"{header}\n\n{text}"


def split_identifier(word: str) -> list[str]:
    """`get_userName2` -> ["get", "user", "name", "2"]. Lowercase."""
    parts: list[str] = []
    for piece in word.split("_"):
        parts.extend(p.lower() for p in _CAMEL.findall(piece))
    return parts


def search_words(text: str) -> str:
    """Words for full-text search: each identifier as written (lowercased) plus its snake_case
    and camelCase parts, so "healthCheck" matches a search for "health check"."""
    out: list[str] = []
    for word in _IDENT.findall(text):
        lower = word.lower()
        out.append(lower)
        parts = split_identifier(word)
        if len(parts) > 1 or (parts and parts[0] != lower):
            out.extend(parts)
    return " ".join(out)


def search_text(path: str, symbol: str | None, text: str) -> str:
    return search_words(f"{path} {symbol or ''} {text}")
