# Project memory

Working memory for any AI tool and for the developer. Read it before every task.

**Rules for this file**
- Update this file at the end of every task.
- Keep it under 150 lines.
- Never store secrets, passwords or API keys here.
- Move old items to the bottom section "Archive".

## Current status

Phases 1 and 2 are merged (last: PR #16). Phase 3 is built on `feat/project-indexing-rag`
(not pushed, no PR yet): indexing, hybrid search and retrieved code in chat, migrations `0005`
and `0006`, 373 tests, 96% coverage of the new code. The dev database `mantle` is still at `0004`
until `alembic upgrade head`. Not done yet: a real-key run of `scripts/eval_retrieval.py`, the
Phase 3 demo with real models, `GET /messages/{id}/context`.
To work: `docker compose up -d` from the project folder, then in `backend`
`.venv\Scripts\Activate.ps1` and `uvicorn app.main:app --reload`.
Open Phase 1/2 items: a cross-provider switch demo (needs a second working key), the Phase 2
demo (memory answers in a new conversation on another model). Keys: free Gemini key works;
OpenAI key valid but no credit (`rate_limited`); no Anthropic or Voyage key.
First demo target: 2026-12-17. Last updated 2026-11-18.

## Done

- 2026-11-17: scaffold, Docker Postgres on 5433, docs, pinned deps + `requirements.lock`, all
  v0.1 tables (`0001`), repositories bound to `user_id`, Fernet helper, seed script (PRs #1–#5).
- 2026-11-18: LLM gateway (PR #7), model switching + context builder + rolling summary (PR #8),
  fixes #9–#12, project memory + pinned items (PR #14, `0004`), memory docs (PRs #15, #16).
  Switch demo 5/5 twice on Gemini 3.8 Flash -> 3.5 Flash Lite (same provider).
- 2026-11-18: `feat/project-indexing-rag` (in review): `0005` (run states/counters/estimate,
  skipped-file rows, segment metadata, `search_tsv` + GIN), `0006` (`code_context_enabled`,
  message context lines); rag `source`, `scanner`, `secret_scan`, `chunker` (tree-sitter),
  `indexer` (incremental, vector reuse by hash, batches, backoff, cancel, resume, startup
  recovery), `search` (RRF k=60); `app/api/projects.py`; ContextBuilder retrieved section;
  SSE `warning`; Gemini embedding with task types; `scripts/eval_retrieval.py`; ADRs 0006, 0007.

## In progress

- `feat/project-indexing-rag`: committed locally, waiting for review and push by the developer.

## Next

The developer decides. Candidates:
1. Run `scripts/eval_retrieval.py` with the Gemini key, then the Phase 3 demo (index the Mantle
   repo, ask "where is the health check timeout set?", switch models, ask again).
2. `GET /messages/{id}/context` (rows exist), then the Phase 2 demo script.
3. `feat/project-profile` (before `feat/teaching-layer`), then `feat/workflow-and-agents`.
4. Not built from api-outline: message cancel, project update/archive/delete.

## Decisions

| Date | Decision | Reason | ADR |
| --- | --- | --- | --- |
| 2026-11-17 | Modular monolith; PostgreSQL + pgvector; LiteLLM behind our gateway; LangGraph only in `workflow` | One user, one system, switching is the core | 0001–0004 |
| 2026-11-17 | Local-first, one default user (fixed id), `user_id` on all user data | Easy path to auth | 0005 |
| 2026-11-17 | Utility model + background rolling summary; switch never calls the old model; unrequested calls logged, visible, can be turned off (D3, D10) | Switching must work when the old model fails; cost | 0003 |
| 2026-11-17 | Version ranges + `requirements.lock`; enums as VARCHAR(32); SET NULL FKs deferrable; usage rows survive deletes | Reproducible; simple migrations | `rules.md`, `data-model.md` |
| 2026-11-18 | SSE events `message_start`, `warning`, `delta`, `message_end`, `error` (`warning` added for retrieval) | User's choice | rule 32 |
| 2026-11-18 | Messages ordered by `sequence`; locks are timestamp columns claimed atomically, stale after 600 s | Timestamps tie in one transaction; survives crashes | `data-model.md` |
| 2026-11-18 | Memory: one `memory_items` table, per-kind statuses in the service; pinned preview served by `conversations` | User's choice; rule 11 | `data-model.md` |
| 2026-11-18 | Embeddings: any provider the gateway supports (D2 amended); default `gemini/gemini-embedding-001` at 1536 dims, task types `RETRIEVAL_DOCUMENT` / `CODE_RETRIEVAL_QUERY` (checked in LiteLLM 1.110.0 source) | Only the Gemini key works; column stays 1536 | D2 |
| 2026-11-18 | rag may call projects; project list/detail routes live in `app/api` and batch the index status; `tests/test_module_boundaries.py` enforces directions | Folder lives on projects; no cycle | 0006 |
| 2026-11-18 | `tree-sitter-language-pack` pinned `>=0.13,<1`: **do not upgrade to 1.x**, it downloads grammars at runtime | Offline tests, no runtime native downloads | 0007 |
| 2026-11-18 | Hybrid search (vector + `simple` full text, RRF k=60) instead of plain vector top-k; no reranker | User's choice; identifiers need exact matches | `architecture.md` J3 |
| 2026-11-18 | A file that looks like it holds a secret is skipped whole (not just the segment); `id_*` skipped literally (rule 48) | Code goes to a third party | `security.md` |
| 2026-11-18 | Skipped files are `documents` rows (status `skipped` + reason); ignored folders/gitignore only counted in the run's `skip_report` | Useful list without thousands of rows | `data-model.md` |
| 2026-11-18 | Segment vectors are reused by sha256(path + symbol + text) and model; a file's hash is set only when all its segments are stored | Cheap edits; resume after a failure | `data-model.md` |
| 2026-11-18 | `INDEX_COST_LIMIT_USD` (1.00) is an app setting; it moves to user settings with auth | One user in v0.1 | `security.md` |
| 2026-11-18 | Handoff preview reuses the code of the newest reply (message contexts), so it makes no embedding call | Preview stays free | `api-outline.md` |
| 2026-11-18 | Project profile not built here; own branch `feat/project-profile` before `feat/teaching-layer` | One topic per branch | `roadmap.md` |

Full decision text: `docs/architecture.md` → Decisions.

## Known issues and gotchas

- **PostgreSQL 17 Windows service listens on 5432.** Keep Docker on 5433 (`role "mantle" does not exist` = wrong server).
- **First DB connection after a container (re)start can take over 2 s**; `/health` may say `"down"` briefly.
- **Docker Desktop can hang; the DB container can stop by itself** (`Exited (255)`). Then
  `alembic` fails with `WinError 1225`. Run `docker compose ps` and `docker compose up -d`.
- **A Fernet key is 44 characters and ends with `=`.** The API won't start without a valid one.
- **PowerShell commands don't work in Git Bash**; in Git Bash use `source .venv/Scripts/activate`.
- **Python/pytest startup is slow on this machine** (6–16 s). The full suite takes 1–2 minutes.
- **`requirements.lock` was made on Windows with Python 3.14**; regenerate with `python -m pip freeze --exclude-editable > requirements.lock`.
- **No LICENSE file yet. `gh` isn't installed**; the developer opens and merges PRs by hand.
- Git "LF will be replaced by CRLF" warnings are harmless. The first commit is named "chunk 0" (pre-rule).
- **Changing `EMBEDDING_DIMENSIONS` needs a new migration** and a re-index; a test catches a
  mismatch. Voyage (1024 dims) stays disabled at 1536. `pgvector` returns numpy arrays.
- **Repositories don't check that a parent row belongs to the same user.** Fix before auth.
- **`litellm` takes ~11 s to import**: lazy import; `LITELLM_LOCAL_MODEL_COST_MAP=True`.
- **LiteLLM wraps mid-stream errors in `MidStreamFallbackError`**; `map_provider_error` unwraps
  it and maps by HTTP status too. The free Gemini tier rate-limits after ~30 calls in a few
  minutes; indexing backs off (`EMBED_RATE_LIMIT_BACKOFF_SECONDS`, doubling, `EMBED_MAX_RETRIES`).
- **Rows created in one transaction share `now()`**: never order by `created_at` to find "newest".
- **The running app must import every model** (`app/db/session.py` imports `app.db.models`);
  `tests/test_app_wiring.py` checks it in a fresh interpreter.
- **Under Starlette/anyio, cancellation hits every later `await`.** Writes after a client
  disconnect run inside `anyio.CancelScope(shield=True)`.
- Tests run Alembic in a separate thread (`env.py` calls `asyncio.run()`).
- **Every write endpoint needs a JSON body** (even `{}`), or `/docs` gets 415.
- **Swagger's "Example Value" is not the real answer**; the real one is under "Server response".
- OpenAI: `auth_failed` = wrong or partial key; `rate_limited` on a tiny test = no credit.
- **Index jobs are in-process `BackgroundTasks`**: with httpx `ASGITransport` they finish before
  the test's request returns. A restart kills them; startup marks them `failed`/`interrupted`.
- **`tests/fixtures/sample_project` is data**: excluded from ruff (`extend-exclude`) and pytest
  (`collect_ignore_glob`). Secret-shaped strings in tests are built at runtime.
- **The search endpoint is dev-only** (404 unless `APP_ENV=development`).
- **Editing files with Python heredocs in Git Bash turned `\n` in code into real newlines** twice;
  use an editor tool for code that contains escape sequences.
- **What FakeProvider tests can't prove:** real summary quality, real token counts, real
  streaming chunks, and real retrieval quality (fake embeddings are bag-of-words). Only
  `scripts/switch_demo.py` and `scripts/eval_retrieval.py` with real keys do.

## Environment notes

- Windows 11, PowerShell 5.1 (Git Bash also available). Python 3.14; venv `backend\.venv`. Code must work on 3.12+.
- Docker container `mantleai-db-1`, image `pgvector/pgvector:pg16` (pgvector 0.8.7), volume `pgdata`.
- `DATABASE_URL=postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/mantle` (local dev only); tests use `mantle_test`.
- API: `uvicorn app.main:app --reload` from `backend` → `http://127.0.0.1:8000` (`/health`, `/docs`).
- GitHub remote: `origin` → `MohammadAnas-07/MantleAI`, default branch `main`.

## Archive

- PR-by-PR detail for Phases 1–2 is in `git log` and the PR descriptions (#1–#16).
- Older decisions, condensed (2026-11-17/18): Docker Postgres on 5433, `/health` DB check 2 s;
  API refuses to start without a valid `MASTER_ENCRYPTION_KEY`; gateway first on its own branch,
  `LiteLLMBackend` vs `FakeProvider` via `get_gateway`; catalog hardcoded from LiteLLM 1.110.0
  data; purpose `key_test`; JSON-only writes (pure ASGI); usage names `chat`+`user`,
  `rolling_summary`+`background`, `switch_summary`+`user`; switch = `POST .../switch-model`, note
  in `context_handoffs.note`, partial reply = status `cancelled`; background summaries off → the
  NEW model writes the summary at switch time; supersede accepts a new or existing decision and a
  superseded decision can't replace another (no loops); duplicate dependency links are ignored;
  success metric ≥ 4 of 5 questions after a switch (`docs/prd.md`); MIT later, 6 phases, 3
  evenings per week (`docs/phases.md`).
