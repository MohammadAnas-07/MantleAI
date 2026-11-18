# rag

Indexes a project's local folder and finds code for prompts. May call `llm` (embeddings) and
`projects` (the project and its folder); see ADR 0006. Other modules use only `service.py`.

- `source.py`: checks the project folder (absolute, exists, readable, not a root or home).
- `scanner.py`: walks the folder (`.gitignore`, forced skips, symlinks never followed, limits)
  and reads one file (binary, encoding, secrets, empty, changed while read). Skip reason codes.
- `secret_scan.py`: sensitive file names and secret-looking content.
- `languages.py`: which files are indexed, and as which language.
- `chunker.py`: splits text into segments (tree-sitter for Python/TS/JS, Markdown by heading,
  line windows otherwise), the embedder input, and the split-identifier search text.
- `indexer.py`: the estimate, the incremental background job (batches, retries, cancel, resume)
  and startup recovery.
- `search.py`: vector and full-text rankings, reciprocal rank fusion, merging nearby results.
- `service.py`: the public interface (source, index, status, documents, search, retrieval for
  the context builder).
- `router.py`, `schemas.py`: the endpoints in `docs/api-outline.md` ("RAG").
