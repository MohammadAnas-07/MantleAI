# ADR 0007: tree-sitter grammars must ship inside the package

Status: Accepted (2026-11-18, `feat/project-indexing-rag`)

## Context

Code is split into segments per function and class with tree-sitter. The grammars come from
`tree-sitter-language-pack`. Version 1.x (1.25.2 when checked) no longer bundles them: the first
parse of a language downloads a native library from the network into
`%LOCALAPPDATA%\tree-sitter-language-pack`. That breaks rule 13 (tests run without network
access), makes indexing depend on a download server, and loads native code fetched at runtime.
Version 0.13.0 ships the grammars inside its wheel (about 17 MB, `abi3`, works on Python 3.14).

## Decision

- Pin `tree-sitter-language-pack>=0.13,<1` together with `tree-sitter>=0.25,<0.26` (and
  `pathspec>=1.1,<2` for `.gitignore` rules).
- **Do not upgrade the language pack to 1.x** unless it can be configured to use only grammars
  installed with the package, with no download, and a test proves indexing works offline.
- When a grammar can't be loaded, or a file has syntax errors, the chunker falls back to line
  windows and records `parse_fallback`, so indexing never fails because of a grammar.

## Alternatives considered

- **The single-language packages** (`tree-sitter-python`, `tree-sitter-typescript`,
  `tree-sitter-javascript`): bundled and small, but three more dependencies to keep in step, and
  Markdown would need a fourth.
- **Language pack 1.x with a prefetch step at install time:** still a network download outside
  pip and the lock file.
- **No tree-sitter, line windows only:** simpler, but segments cut through functions and lose the
  symbol name that search uses.

## Consequences

- The wheel is larger than the code it is used for (it bundles many languages we don't split).
- Its extra dependencies (`tree-sitter-yaml`, `tree-sitter-c-sharp`,
  `tree-sitter-embedded-template`) appear in `requirements.lock`.
