# Project memory

Working memory for any AI tool and for the developer. Read it before every task.

**Rules for this file**
- Update this file at the end of every task.
- Keep it under 150 lines.
- Never store secrets, passwords or API keys here.
- Move old items to the bottom section "Archive".

## Current status

**Status (2026-11-25).** `docs/readme-screenshots` (not pushed): 6 real screenshots in
`landing/public/screenshots/` (demo project on the public sample fixture, deleted afterwards; 5
Gemini calls), README gets a live link, CI badge, Screenshots section and merged list limits.
Landing page live at <https://mohammadanas-07.github.io/MantleAI/> (`pages.yml`).

**Audit 2026-11-20** (A-001..A-022, report outside the repo).
- Fixed and merged: A-001..A-011, A-012 (backup notes), A-013, A-014, A-017..A-019, A-021, A-022.
- Open: A-015 dead code and A-016 boundary test (task 9 items 1-2, not done yet; keep
  `ProjectProfileRepository.get_for_project`, now used); A-020 bundle and list limits (task 8).
- Deferred: A-012 separate app role, `scripts/backup.ps1`.

**Summary.** Built: projects, keys, streaming chat, model switching, project memory, cited
retrieval, profile facts, gap finder, the workflow page with Planner and Reviewer runs. Not
built: teaching layer (notes, concepts list), model-written profile summary, `GET /audit-events`,
`GET /messages/{id}/context`. Branches: 2 local (`main`, `docs/readme-screenshots`), 1 remote (merged ones deleted).
`scripts/agent_demo.py` on a lite Gemini model: valid Planner and Reviewer output, one sample
(quality not proven). Agent run on `gemini-3.8-flash` timed out at 120 s; chat timeout unconfirmed.

Tests 2026-11-24 (database up): backend 883 passed, none skipped;
frontend 142 passed (2026-11-24), `gen:api:check` up to date. Last run with the database: 883 passed,
profile races 5/5 (2026-11-21). pytest needs `TEST_DATABASE_URL`. Migration head `0011`
(`alembic upgrade head`). To work: `docker compose up -d`; `backend`: `.venv\Scripts\Activate.ps1`,
`uvicorn app.main:app --reload`; `frontend`: `npm run dev`. Keys: free Gemini works; OpenAI
valid but no credit; no Anthropic or Voyage key. Demo target 2026-12-17. Updated 2026-11-24.

## Done

- 2026-11-17/18: scaffold, Postgres 5433, tables, Fernet, seed, LLM gateway, switching, context
  builder, rolling summary, memory. Switch demo 5/5 twice on Gemini (no result file saved).
- 2026-11-18: indexing and RAG (hybrid search, RRF k=60, ADRs 0006, 0007); the first frontend
  (`docs/design-app.md`, settings, projects, index, memory, chat, context, activity).
- 2026-11-19/21: quota fix (`0007`); workflow and agents (`0008`, plain state machine, approval
  of drafts, 5 review fixes, rules 85-90); the workflow UI; audit fixes (`0009`, `0010`; races in
  `tests/test_run_races.py`, query counts in `tests/query_count.py`); safe sources and scan caps;
  the project profile facts (`0011`, Profile tab, `<project_profile>` block).
- 2026-11-24: license fields, CI (880 passed, 3 skipped), app redesign, flaky test fix.

## In progress

- Click eval (25 questions): run 1 stopped at 926/1,429 segments (Gemini daily limit); resume.

## Next

The developer decides. Candidates: more real plan runs on a lite Gemini model, then the Phase 4
demo; the click eval and the Phase 3 demo; `GET /messages/{id}/context` and the Phase 2 demo;
`feat/profile-summary` or `feat/teaching-layer`. Not built: message cancel, typed `dict`
responses, `POST /memory/{id}/approve|reject`.

## Known cleanup

- `list_gap_runs`/`runs.list_runs` repeat a query; `memory_trimmed` has two shapes (not audited).
- `test_agent_runs.py::test_step_timeout` (0.01 s timeout) failed once in a full run; flaky.

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
| 2026-11-18 | UI first without workflow and teaching screens (they follow Phase 4) | User's choice | `design-app.md` |
| 2026-11-24 | App design replaced: calm ink-on-white system, light default, no webfonts, one blue accent | User's choice | `design-app.md` |
| 2026-11-24 | Landing page uses the same tokens with an editorial brief; the grunge direction is dropped, and architecture.md C1 and C3 are resolved | User's choice | `design-landing.md` |
| 2026-11-18 | TypeScript 5.9 (toolchain support); API types generated from OpenAPI and committed, `gen:api:check` guards them, operationId = route function name | Builds without a backend | `api-outline.md` |
| 2026-11-19 | Used-up quota = per-day quota id or requested wait > 10 min; anything else stays `rate_limited`; `error_detail` keeps only sanitized structured fields | No guessing; provider text can echo prompts | rule 51 |
| 2026-11-19 | No LangGraph: Planner -> Reviewer -> user approval as a plain state machine in PostgreSQL; no revision loop; reopen replaces request-changes; gap finder is an analysis call, not a third agent; purpose `agent_run` | User's choice; two fixed steps | 0004 |
| 2026-11-19 | Workflow GET writes nothing (state stored on first change); approve/skip take `stage_id`; drafts saved only on approval, tasks `todo`, decisions `proposed` | Rule 28; one of two racing approvals must lose | `api-outline.md` |
| 2026-11-20 | Workflow UI is its own page in the workspace; the estimate comes from `POST .../agent-runs/estimate` before a confirm; proposed decisions are accepted through `PATCH /memory/{id}` (status) | The AI panel is too narrow for the approval list; no start without a real number | `api-outline.md` |
| 2026-11-18 | Allowed hosts localhost/127.0.0.1 any port (400 `invalid_host`); CORS only the dev origins; project default model lives in project settings | DNS rebinding; user's choice | `security.md` |

## Known issues and gotchas

- **PostgreSQL 17 on Windows uses 5432**; Docker stays on 5433. First DB connect can take 2 s+; the
  container can exit (`WinError 1225`): `docker compose up -d`. A Fernet key is 44 chars, ends `=`.
- **PowerShell commands don't work in Git Bash** (`source .venv/Scripts/activate`); the suite takes 2 min.
- **`requirements.lock` was made on Windows with Python 3.14**; regenerate with `python -m pip freeze --exclude-editable > requirements.lock`.
- **MIT LICENSE added 2026-11-22** (repo not public yet). `gh` 2.105.0 is installed and logged in (`gh auth status`), but the
  developer opens and merges PRs. CRLF warnings are harmless; the first commit is named "chunk 0" (pre-rule).
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
  the app's own session (the test DB). Switch `get_current_user_id` instead. Concurrency tests
  commit to `mantle_test` and clean up. `defang` turns `</source>` into `&lt;/source>`.
- **MSW 3 renamed `onUnhandledRequest` to `onUnhandledFrame`**. Backend tests use `http://localhost`.
- **`pytest -s` hangs in this shell**: write debug output to a file instead.
- **PostgreSQL error text can quote the bad value** even with `hide_parameters`: log types only.
- **Tailwind text scale is overridden**: `text-sm` 13px, `text-base` 14px. Tests: no Windows paths by hand; don't split matched sentences into spans.
- **Testing Library role queries are slow on a long plan**: wait for a text first, then
  `getByRole`. A file's first full-page render can pass 1 s: give its `findBy*` `{ timeout: 5_000 }`. Hidden "sr-only" prefixes lose their space in jsdom names: use `aria-label`.
- **What FakeProvider tests can't prove:** real summary, plan and review quality, real token
  counts and streaming, retrieval quality (fake embeddings are bag-of-words). Only the scripts
  (`switch_demo.py`, `eval_retrieval.py`, `agent_demo.py`) with real keys do.

## Environment notes

- Windows 11, PowerShell 5.1 (Git Bash also available). Python 3.14; venv `backend\.venv`. Code must work on 3.12+.
- Docker container `mantleai-db-1`, image `pgvector/pgvector:pg16` (pgvector 0.8.7), volume `pgdata`.
- `DATABASE_URL=...5433/mantle` (dev only); tests use `TEST_DATABASE_URL=...5433/mantle_test`.
- API: `uvicorn app.main:app --reload` (`backend`) → `http://127.0.0.1:8000`; Node 24.18 / npm 11.16,
  `npm run dev` (`frontend`) → `http://127.0.0.1:5173`.
- GitHub remote: `origin` → `MohammadAnas-07/MantleAI`, default branch `main`.

## Archive

- Detail for Phases 1–2 is in `git log` and the pull request descriptions.
- Older decisions (2026-11-17/18): `/health` DB check 2 s; no start without a valid master key;
  `FakeProvider` via `get_gateway`; switch = `POST .../switch-model` (partial reply `cancelled`;
  summaries off -> the NEW model summarises); success metric >= 4 of 5; 6 phases.
- Indexing (2026-11-18): skipped files are `documents` rows; vectors reused by sha256(path +
  symbol + text) and model; `INDEX_COST_LIMIT_USD` is an app setting until auth.
