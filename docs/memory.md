# Project memory

Working memory for any AI tool and for the developer. Read it before every task.

**Rules for this file**
- Update this file at the end of every task.
- Keep it under 150 lines.
- Never store secrets, passwords or API keys here.
- Move old items to the bottom section "Archive".

## Current status

**Summary (2026-11-20).** Mantle today: projects, keys, chat with streaming, model switching
with handoff, project memory, indexing with cited retrieval, and the workflow with gap finder,
Planner and Reviewer, and the workflow page (stages, gap finder, agent runs, approval; merged).
An audit (2026-11-20, report outside the repo, A-001..A-022) found 2 Critical, 3 High issues.
`fix/test-database-guard` (not pushed) fixes A-001: tests use only `TEST_DATABASE_URL` (name
ends in `_test`) and stop with exit 4 otherwise. Next fix branches: secret detection,
untrusted output and prompts, error handling and logs, run concurrency, docs catch-up. Not
built: teaching notes, project profile, `GET /messages/{id}/context`, message cancel. Not run
with a real model: a Planner/Reviewer run (seen `provider_unavailable` once), the click eval.
Next: the developer adds `TEST_DATABASE_URL` to `backend/.env`; then `fix/index-secret-detection`.
Branches: 2 local (`main`, `fix/test-database-guard`), 27 remote (untouched).

Tests: 579 backend (97% coverage) and 96 frontend pass. pytest needs `TEST_DATABASE_URL`.
Migration head `0008` (`alembic upgrade head`). To work: `docker compose up -d`; `backend`:
`.venv\Scripts\Activate.ps1`, `uvicorn app.main:app --reload`; `frontend`: `npm run dev`.
Keys: free Gemini works; OpenAI valid but no credit; no Anthropic or Voyage key.
First demo target: 2026-12-17. Last updated 2026-11-20 (test database guard).

## Done

- 2026-11-17/18: scaffold, Docker Postgres 5433, docs, tables, Fernet, seed; LLM gateway, model
  switching, context builder, rolling summary, project memory. Switch demo 5/5 twice on Gemini.
- 2026-11-18: indexing and RAG (hybrid search, RRF k=60, ADRs 0006, 0007); the first frontend
  (`docs/design-app.md`, settings, projects, index, memory, chat, context, activity).
- 2026-11-19: daily quota fix (`0007`); `feat/workflow-and-agents` merged: `0008`, stages YAML,
  gates, events, gap finder, Planner + Reviewer as a plain state machine, approval of drafts,
  and 5 review fixes (run lock, conditional cancel, attribute escaping, unpriced models, limit
  checks); rules 85-90.

## In progress

- `fix/test-database-guard`: `tests/db_guard.py` (check, `guarded_engine`), `pytest_configure`
  swaps the app's `DATABASE_URL` for the test URL; no auto-create of the test database.
- Workflow UI (merged 2026-11-20): next is one real plan run in the browser.
- Click eval (`eval_retrieval.py`, 25 questions): run 1 stopped at 926/1,429 segments
  (Gemini daily limit); resume.

## Next

The developer decides (full decision text: `docs/architecture.md`). Candidates:
1. A real plan run in the UI with Gemini (checklist in the PR), then the Phase 4 demo.
2. Run the click eval, then the Phase 3 demo (index the Mantle repo, ask, switch, ask again).
3. `GET /messages/{id}/context`, then the Phase 2 demo script.
4. `feat/project-profile` (before `feat/teaching-layer`).
5. Not built: message cancel, project description/archive, typed models for `dict` responses
   (agent run `result`, `estimate`, `warnings`), `POST /memory/{id}/approve|reject`.

## Known cleanup

- Run list endpoints load steps with one query per run (N+1); transitions load memory twice.
- `list_gap_runs` and `runs.list_runs` duplicate one query; `memory_trimmed` has two shapes.
- Workflow GET returns every event (no paging); the UI shows the latest 20 and a "show all".

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
| 2026-11-18 | UI first without workflow and teaching screens (they follow Phase 4); app design "grunge-lite" | User's choice | `design-app.md` |
| 2026-11-18 | TypeScript 5.9 (toolchain support); API types generated from OpenAPI and committed, `gen:api:check` guards them, operationId = route function name | Builds without a backend | `api-outline.md` |
| 2026-11-19 | Used-up quota = per-day quota id or requested wait > 10 min; anything else stays `rate_limited`; `error_detail` keeps only sanitized structured fields | No guessing; provider text can echo prompts | rule 51 |
| 2026-11-19 | No LangGraph: Planner -> Reviewer -> user approval as a plain state machine in PostgreSQL; no revision loop; reopen replaces request-changes; gap finder is an analysis call, not a third agent; purpose `agent_run` | User's choice; two fixed steps | 0004 |
| 2026-11-19 | Workflow GET writes nothing (state stored on first change); approve/skip take `stage_id`; drafts saved only on approval, tasks `todo`, decisions `proposed` | Rule 28; one of two racing approvals must lose | `api-outline.md` |
| 2026-11-20 | Workflow UI is its own page in the workspace; the estimate comes from `POST .../agent-runs/estimate` before a confirm; proposed decisions are accepted through `PATCH /memory/{id}` (status) | The AI panel is too narrow for the approval list; no start without a real number | `api-outline.md` |
| 2026-11-18 | Allowed hosts localhost/127.0.0.1 any port (400 `invalid_host`); CORS only the dev origins; project default model lives in project settings | DNS rebinding; user's choice | `security.md` |

## Known issues and gotchas

- **PostgreSQL 17 Windows service listens on 5432**; keep Docker on 5433. The first DB connection
  after a restart can take over 2 s. The container can stop by itself (`Exited (255)`, then
  `WinError 1225`): `docker compose ps`, `docker compose up -d`. A Fernet key is 44 chars, ends `=`.
- **PowerShell commands don't work in Git Bash** (`source .venv/Scripts/activate`); the suite takes 2 min.
- **`requirements.lock` was made on Windows with Python 3.14**; regenerate with `python -m pip freeze --exclude-editable > requirements.lock`.
- **No LICENSE yet. `gh` isn't installed**: the developer opens and merges PRs. CRLF warnings
  are harmless; the first commit is named "chunk 0" (pre-rule).
- **Changing `EMBEDDING_DIMENSIONS` needs a new migration** and a re-index; a test catches a
  mismatch. Voyage (1024 dims) stays disabled at 1536. `pgvector` returns numpy arrays.
- **Repositories don't check a parent row's user** (fix before auth); `litellm` imports lazily (~11 s).
- **LiteLLM wraps mid-stream errors in `MidStreamFallbackError`**; `map_provider_error` unwraps
  it. Free Gemini rate-limits after ~30 calls in minutes. **For a Gemini 429 LiteLLM drops headers
  and body** (JSON only in the message); `provider_errors.py` reads `quotaId`/`retryDelay` there.
- **Rows in one transaction share `now()`** (never order by `created_at` for "newest"). **The
  running app must import every model** (`app/db/session.py` imports `app.db.models`);
  `tests/test_app_wiring.py` checks it in a fresh interpreter.
- **Under anyio, cancellation hits every later `await`**: post-disconnect writes use `CancelScope(shield=True)`.
- **Every write endpoint needs a JSON body** (even `{}`), or `/docs` and the frontend get 415.
- **Index jobs and agent runs are in-process `BackgroundTasks`**: in tests they finish before the
  request returns; a restart kills them (startup marks them `interrupted`). Search is dev-only.
- **`tests/fixtures/sample_project` is data**; the click eval repo is `C:\Users\admin\Desktop\click-sample`.
- **`core.autocrlf=true` checks fixtures out with CRLF**: tests must not assume LF in `tests/fixtures`.
- **Python heredocs in Git Bash turn `\n` in code into real newlines** (three times): use the Edit tool.
- **Several uvicorns can listen on 8000; the oldest answers** (`netstat -ano | findstr :8000`).
  An unhandled 500 has no CORS headers, so the browser shows "Can't reach the API".
- **Leaving a nested `api_client` clears ALL dependency overrides**: the outer client then uses
  the app's own session (now the test DB, since the guard). Switch `get_current_user_id` instead.
  Concurrency tests commit to `mantle_test`
  and clean up. `defang` turns `</source>` into `&lt;/source>` (the `>` stays).
- **MSW 3 renamed `onUnhandledRequest` to `onUnhandledFrame`**. Backend tests use `http://localhost`.
- **Testing Library role queries are slow on a long plan**: wait for a text first, then
  `getByRole`. Hidden "sr-only" prefixes lose their space in jsdom names: use `aria-label`.
- **What FakeProvider tests can't prove:** real summary, plan and review quality, real token
  counts and streaming, retrieval quality (fake embeddings are bag-of-words). Only the scripts
  (`switch_demo.py`, `eval_retrieval.py`, `agent_demo.py`) with real keys do.

## Environment notes

- Windows 11, PowerShell 5.1 (Git Bash also available). Python 3.14; venv `backend\.venv`. Code must work on 3.12+.
- Docker container `mantleai-db-1`, image `pgvector/pgvector:pg16` (pgvector 0.8.7), volume `pgdata`.
- `DATABASE_URL=...5433/mantle` (dev only); tests use `TEST_DATABASE_URL=...5433/mantle_test`.
- API: `uvicorn app.main:app --reload` from `backend` → `http://127.0.0.1:8000` (`/health`, `/docs`).
- Frontend: Node 24.18 / npm 11.16; `npm run dev` from `frontend` → `http://127.0.0.1:5173`.
- GitHub remote: `origin` → `MohammadAnas-07/MantleAI`, default branch `main`.

## Archive

- Detail for Phases 1–2 is in `git log` and the pull request descriptions.
- Older decisions, condensed (2026-11-17/18): `/health` DB check 2 s; no start without a valid
  `MASTER_ENCRYPTION_KEY`; `LiteLLMBackend` vs `FakeProvider` via `get_gateway`; catalog from
  LiteLLM 1.110.0; JSON-only writes; switch = `POST .../switch-model` (note in
  `context_handoffs.note`, partial reply `cancelled`; summaries off -> the NEW model summarises);
  supersede can't loop; duplicate links ignored; success metric >= 4 of 5 after a switch; MIT
  later, 6 phases, 3 evenings per week.
