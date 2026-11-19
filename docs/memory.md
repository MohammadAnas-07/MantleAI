# Project memory

Working memory for any AI tool and for the developer. Read it before every task.

**Rules for this file**
- Update this file at the end of every task.
- Keep it under 150 lines.
- Never store secrets, passwords or API keys here.
- Move old items to the bottom section "Archive".

## Current status

Phases 1-3 are merged, and Phase 5's first UI too: `frontend/` (React,
Vite, TS strict, Tailwind, grunge-lite design), 48 frontend tests; backend CORS, Host check,
project PATCH and DELETE, operation ids, `GET /usage/records`; 396 backend tests. All checks
pass on `main` after the merge. Dev database `mantle` at `0006`.
Phase 3 real-key eval (2026-11-18): recall@5 vector 1.00 / text 0.95 / hybrid 1.00. Not done:
the Phase 3 demo with real models, `GET /messages/{id}/context`, Phase 4 (workflow, teaching).
To work: `docker compose up -d`; `backend`: `.venv\Scripts\Activate.ps1`,
`uvicorn app.main:app --reload`; `frontend`: `npm run dev` (http://127.0.0.1:5173).
Keys: free Gemini works; OpenAI valid but no credit; no Anthropic or Voyage key.
First demo target: 2026-12-17. Last updated 2026-11-19.

## Done

- 2026-11-17: scaffold, Docker Postgres on 5433, docs, pinned deps + `requirements.lock`, all
  v0.1 tables (`0001`), repositories bound to `user_id`, Fernet helper, seed script.
- 2026-11-18: LLM gateway, model switching + context builder + rolling summary, four small
  fixes, project memory + pinned items (`0004`), memory docs.
  Switch demo 5/5 twice on Gemini 3.8 Flash -> 3.5 Flash Lite (same provider).
- 2026-11-18: `feat/project-indexing-rag` (merged): `0005` (run states/counters/estimate,
  skipped-file rows, segment metadata, `search_tsv` + GIN), `0006` (`code_context_enabled`,
  message context lines); rag `source`, `scanner`, `secret_scan`, `chunker` (tree-sitter),
  `indexer` (incremental, vector reuse by hash, batches, backoff, cancel, resume, startup
  recovery), `search` (RRF k=60); `app/api/projects.py`; ContextBuilder retrieved section;
  SSE `warning`; Gemini embedding with task types; `scripts/eval_retrieval.py`; ADRs 0006, 0007.
  `fix/crlf-fixture-test`: the identical-file test is line-ending independent.
- 2026-11-18: `feat/frontend-workspace` (merged): `docs/design-app.md`; frontend (settings,
  projects, index, memory, chat with SSE streaming, context preview, switching, activity log);
  backend CORS + Host check, project PATCH/DELETE, operation ids, `/usage/records`,
  `scripts/export_openapi.py`; frontend rules in `CLAUDE.md` and `rules.md` (77-84).

## In progress

- Nothing.

## Next

The developer decides. Candidates:
1. The Phase 3 demo (index the Mantle repo, ask "where is the health check timeout set?",
   switch models, ask again). The eval is done; a bigger eval set would show hybrid's value.
2. `GET /messages/{id}/context` (rows exist), then the Phase 2 demo script.
3. `feat/project-profile` (before `feat/teaching-layer`), then `feat/workflow-and-agents`.
4. Not built: message cancel, project description/archive; API gaps from the UI work (typed
   models for `dict` responses, CORS on 500s) are listed in the frontend PR description.

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
| 2026-11-18 | UI first without workflow and teaching screens (they follow Phase 4); app design "grunge-lite" | User's choice | `design-app.md` |
| 2026-11-18 | TypeScript 5.9 (not 7): openapi-typescript and typescript-eslint support only up to 6.x/5.x | Toolchain support | `frontend/package.json` |
| 2026-11-18 | API types generated from OpenAPI and committed; `gen:api:check` guards them; operationId = route function name | Builds without a backend; stable names | `api-outline.md` |
| 2026-11-18 | Allowed hosts localhost/127.0.0.1 any port (400 `invalid_host`); CORS only the dev origins; project default model lives in project settings | DNS rebinding; user's choice | `security.md` |

Full decision text: `docs/architecture.md` → Decisions.

## Known issues and gotchas

- **PostgreSQL 17 Windows service listens on 5432.** Keep Docker on 5433 (`role "mantle" does not exist` = wrong server).
- **First DB connection after a container (re)start can take over 2 s**; `/health` may say `"down"` briefly.
- **Docker Desktop can hang; the DB container can stop by itself** (`Exited (255)`). Then
  `alembic` fails with `WinError 1225`. Run `docker compose ps` and `docker compose up -d`.
- **A Fernet key is 44 characters and ends with `=`.** The API won't start without a valid one.
- **PowerShell commands don't work in Git Bash** (use `source .venv/Scripts/activate`). Python
  and pytest start slowly here (6-16 s); the backend suite takes 1-2 minutes.
- **`requirements.lock` was made on Windows with Python 3.14**; regenerate with `python -m pip freeze --exclude-editable > requirements.lock`.
- **No LICENSE yet. `gh` isn't installed**: the developer opens and merges PRs. CRLF warnings
  are harmless; the first commit is named "chunk 0" (pre-rule).
- **Changing `EMBEDDING_DIMENSIONS` needs a new migration** and a re-index; a test catches a
  mismatch. Voyage (1024 dims) stays disabled at 1536. `pgvector` returns numpy arrays.
- **Repositories don't check a parent row's user** (fix before auth); `litellm` imports lazily (~11 s).
- **LiteLLM wraps mid-stream errors in `MidStreamFallbackError`**; `map_provider_error` unwraps
  it and maps by HTTP status too. The free Gemini tier rate-limits after ~30 calls in a few
  minutes; indexing backs off (`EMBED_RATE_LIMIT_BACKOFF_SECONDS`, doubling, `EMBED_MAX_RETRIES`).
- **Rows in one transaction share `now()`** (never order by `created_at` for "newest"). **The
  running app must import every model** (`app/db/session.py` imports `app.db.models`);
  `tests/test_app_wiring.py` checks it in a fresh interpreter.
- **Under Starlette/anyio, cancellation hits every later `await`.** Writes after a client
  disconnect run inside `anyio.CancelScope(shield=True)`.
- Tests run Alembic in a separate thread. **Every write endpoint needs a JSON body** (even `{}`),
  or `/docs` and the frontend get 415. Swagger's "Example Value" is not the real answer.
- **Index jobs are in-process `BackgroundTasks`**: in tests they finish before the request
  returns; a restart kills them (startup marks them `interrupted`). Search is dev-only.
- **`tests/fixtures/sample_project` is data**: excluded from ruff (`extend-exclude`) and pytest
  (`collect_ignore_glob`). Secret-shaped strings in tests are built at runtime.
- **`core.autocrlf=true` checks the fixture out with CRLF.** Tests must not assume LF in
  `tests/fixtures` (a test that turned LF into CRLF made CR CR LF and failed on main).
- **Editing files with Python heredocs in Git Bash turned `\n` in code into real newlines** twice;
  use an editor tool for code that contains escape sequences.
- **Windows lets several uvicorns listen on port 8000; the oldest answers.** An old one without
  CORS makes the UI say "Can't reach the API". Keep one; check `netstat -ano | findstr :8000`.
- **An unhandled 500 has no CORS headers** (Starlette's error middleware sits outside CORS), so
  the browser shows a network error. Happens on the slow first DB connection after a restart.
- **MSW 3 renamed `onUnhandledRequest` to `onUnhandledFrame`** (the old name is ignored). Backend
  tests use `base_url="http://localhost"`: the Host check refuses other names.
- **What FakeProvider tests can't prove:** real summary quality, real token counts, real
  streaming chunks, and real retrieval quality (fake embeddings are bag-of-words). Only
  `scripts/switch_demo.py` and `scripts/eval_retrieval.py` with real keys do.

## Environment notes

- Windows 11, PowerShell 5.1 (Git Bash also available). Python 3.14; venv `backend\.venv`. Code must work on 3.12+.
- Docker container `mantleai-db-1`, image `pgvector/pgvector:pg16` (pgvector 0.8.7), volume `pgdata`.
- `DATABASE_URL=postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/mantle` (local dev only); tests use `mantle_test`.
- API: `uvicorn app.main:app --reload` from `backend` → `http://127.0.0.1:8000` (`/health`, `/docs`).
- Frontend: Node 24.18 / npm 11.16; `npm run dev` from `frontend` → `http://127.0.0.1:5173`.
- GitHub remote: `origin` → `MohammadAnas-07/MantleAI`, default branch `main`.

## Archive

- Detail for Phases 1–2 is in `git log` and the pull request descriptions.
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
