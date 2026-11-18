# Project memory

Working memory for any AI tool and for the developer. Read it before every task.

**Rules for this file**
- Update this file at the end of every task.
- Keep it under 150 lines.
- Never store secrets, passwords or API keys here.
- Move old items to the bottom section "Archive".

## Current status

Phase 1's core feature works with real models. Phase 2 (project memory) is merged (PR #14,
`4721577`) and recorded in docs (PR #15, `fc37e28`); 270 tests. The dev database `mantle` is at
migration `0004`. To work: `docker compose up -d` from the project folder, then in `backend`
`.venv\Scripts\Activate.ps1` and `uvicorn app.main:app --reload`.
Left for Phase 2: the demo (memory answers in a new conversation on another model) and the
per-message "sources used" view.
**Switch demo 2026-11-18: 5/5 PASS twice**, Gemini 3.8 Flash -> Gemini 3.5 Flash Lite. Run 1:
all 12 messages verbatim. Run 2 (`SUMMARY_TRIGGER_TOKENS=200`): summary of #1-#6 (198 tokens,
decisions 1-3 with reasons) + #7-#12 verbatim; B still 5/5, so the summary path works with real
models; the next summary was incremental and kept all reasons.
Only open Phase 1 item: a cross-provider switch (the docs' demo, e.g. Claude -> GPT). Keys: the
free Gemini key works; the OpenAI key is valid but has no credit (`rate_limited`); no Anthropic
key. A later demo run failed on turn 1 with Gemini 503 (Google overloaded); retry later.
First demo target: 2026-12-17.
Last updated 2026-11-18.

## Done

- 2026-11-17: scaffold, `/health`, Docker Postgres on 5433, PRs #1–#4 (docs, localhost binding,
  product docs, pinned dependencies + `requirements.lock`).
- 2026-11-17: `feat/database-models` (PR #5): all v0.1 tables, async Alembic `0001`, repositories
  bound to `user_id`, Fernet helper, seed script, tests on `mantle_test`.
- 2026-11-18: `feat/llm-gateway` (PR #7): `modules/llm/gateway.py` (one usage row per call, also
  on error/cancel), `litellm_backend.py` (only litellm importer, lazy), `fake.py` (FakeProvider,
  call log), typed errors, seeded model catalog, migration `0002` (`supports_tools`), `app/api/`
  (error shape, JSON-only middleware, `/me`), llm endpoints, key-masking log filter.
- 2026-11-18: `feat/model-switching` (PR #8): `conversations/context_builder.py` (budget =
  window - reserved output - 10% margin; drop order retrieved → oldest messages → summary → pinned),
  `prompts/system_v1.txt` + `summary_v1.txt`, `summary.py` (incremental, lock, error stored),
  `suggestions.py`, `service.py` + `router.py` (conversations, SSE messages, summary,
  handoff-preview, switch-model, handoffs), minimal projects endpoints, `projects/service.py`
  (pinned items, read-only), migration `0003` (message `sequence`, summary range, locks, handoff
  `note`), `backend/scripts/switch_demo.py` + `.yaml`. Fix: the app now registers every model.
- 2026-11-18: PR #9 (memory after the merge); PR #10 `fix/key-test-from-docs` (the key test
  endpoint takes `{}` so `/docs` sends JSON); PR #11 `feat/second-gemini-model` (Gemini 3.5 Flash
  Lite + demo results); PR #12 `fix/unwrap-stream-errors` (mid-stream 429 reported as
  `rate_limited`; logs show root type and HTTP status).
- 2026-11-18: `feat/project-memory` (PR #14): migration `0004` (per-kind statuses and
  priorities, decision `why`/`alternatives`/`decided_at`/`superseded_by_id`, `memory_dependencies`
  table), `projects/memory_service.py` (validation, item limit, supersede, dependency cycles),
  `projects/schemas.py`, memory routes, `projects/pinned.py` (selection, caps, share of budget,
  deterministic one-line text, delimiter defanging), pinned info in handoff preview and note,
  `GET /projects/{id}/memory/pinned`. `pytest-cov` added. Coverage of the projects module: 99%.

## In progress

- Nothing.

## Next

The developer decides what comes next. Candidates:
1. The Phase 2 demo: 3 decisions + 2 tasks as memory, a NEW conversation on another model answers
   the 5 questions from memory alone (with the free Gemini key: Gemini 3.8 Flash and 3.5 Flash
   Lite). No script exists for it yet; `scripts/switch_demo.py` tests a switch, not memory.
2. A cross-provider switch demo, once a second provider key works (closes Phase 1 fully).
3. Not built yet from api-outline: `POST /messages/{id}/cancel`, `GET /messages/{id}/context`,
   project update/archive/delete.

## Decisions

| Date | Decision | Reason | ADR |
| --- | --- | --- | --- |
| 2026-11-17 | Modular monolith; PostgreSQL + pgvector; LiteLLM behind our gateway; LangGraph only in `workflow` | One user, one system, switching is the core | 0001–0004 |
| 2026-11-17 | Local-first, one default user (fixed id `...0001`, made by the seed script), `user_id` on all user data | Easy path to auth | 0005 (amended) |
| 2026-11-17 | Docker Postgres on host port 5433; `/health` DB check limited to 2 s | Windows PG17 uses 5432; answer fast | — |
| 2026-11-17 | Embeddings via OpenAI or Voyage; utility model + background rolling summary; switch never calls the old model (D2, D3) | Switching must work when the old model fails | 0002, 0003 |
| 2026-11-17 | Unrequested LLM calls are logged, visible, can be turned off; concepts list has no LLM (D10) | Background calls cost money | 0003 |
| 2026-11-17 | Open source (MIT later), not hosted in v0.1, 6 phases, 3 evenings per week | Author's choice; prove the core first | `docs/phases.md` |
| 2026-11-17 | Success = ≥ 4 of 5 decision questions right after a switch, < 1 min, no re-explaining | Testable metric | `docs/prd.md` |
| 2026-11-17 | Version ranges + `requirements.lock`; enums as VARCHAR(32); SET NULL FKs deferrable | Reproducible; simple migrations; safe cascades | `docs/rules.md`, `data-model.md` |
| 2026-11-17 | Messages are provider-neutral content parts; usage rows survive deletes | Any provider; complete cost history | `docs/data-model.md` |
| 2026-11-17 | API refuses to start without a valid `MASTER_ENCRYPTION_KEY` | Fail fast | `docs/security.md` |
| 2026-11-18 | Gateway first, own branch; `LiteLLMBackend` vs `FakeProvider` via `get_gateway` | One topic per branch; tests need no keys | 0003 |
| 2026-11-18 | Catalog hardcoded from LiteLLM 1.110.0 data; purpose `key_test`; JSON-only writes (pure ASGI) | Offline seeding; every call logged; SSE-safe | — |
| 2026-11-18 | SSE events `message_start`, `delta`, `message_end`, `error` | User's choice | `docs/rules.md` #32 |
| 2026-11-18 | Usage names from data-model: `chat`+`user`, `rolling_summary`+`background`, `switch_summary`+`user` | Matches rule 35 and D10 | `docs/data-model.md` |
| 2026-11-18 | Switch = `POST .../switch-model`; handoff note in `context_handoffs.note`; partial reply = status `cancelled` | Docs' shape | `docs/api-outline.md` |
| 2026-11-18 | Background summaries off → the NEW model writes the summary at switch time | Never call the old model | — |
| 2026-11-18 | Messages ordered by `sequence`; current summary = highest `to_sequence` | Timestamps tie within one transaction | `docs/data-model.md` |
| 2026-11-18 | Locks as timestamp columns claimed with one atomic UPDATE; stale after 600 s | Simple, testable, survives crashes | `docs/data-model.md` |
| 2026-11-18 | Minimal project endpoints (list, create, get) added in `feat/model-switching` | Needed to create conversations via the API | — |
| 2026-11-18 | Memory stays ONE `memory_items` table; per-kind statuses/priorities checked in the service; new columns + `memory_dependencies` | User's choice; least churn | `docs/data-model.md` |
| 2026-11-18 | Memory paths follow api-outline (`/projects/{id}/memory`, `/memory/{id}`) + supersede, dependencies, pinned preview; approve/reject wait for Phase 4 | User's choice | `docs/api-outline.md` |
| 2026-11-18 | Supersede accepts a new decision or an existing one; a superseded decision can't replace another, which rules out loops | One simple check covers every loop | — |
| 2026-11-18 | Duplicate dependency links are ignored (no error) | Idempotent, consistent | — |
| 2026-11-18 | Pinned preview is served by `conversations` (needs the model's token counter); `projects` gets the counter passed in | Rule 11: projects calls no module | — |

Full decision text: `docs/architecture.md` → Decisions.

## Known issues and gotchas

- **PostgreSQL 17 Windows service listens on 5432.** Keep Docker on 5433 (`role "mantle" does not exist` = wrong server).
- **First DB connection after a container (re)start can take over 2 s**; `/health` may say `"down"` briefly.
- **Docker Desktop is sometimes slow or hangs; the DB container can stop by itself** (`Exited (255)`).
  Then `alembic` fails with `WinError 1225`. Run `docker compose ps` and `docker compose up -d`.
- **A Fernet key is 44 characters and ends with `=`.** The API won't start without a valid one.
- **PowerShell commands don't work in Git Bash** (`.venv\Scripts\Activate.ps1`); in Git Bash use `source .venv/Scripts/activate`.
- **Python/pytest startup is slow on this machine** (6–16 s). Not a test problem.
- **`requirements.lock` was made on Windows with Python 3.14**; regenerate with `python -m pip freeze --exclude-editable > requirements.lock`.
- **No LICENSE file yet. `gh` isn't installed**; the developer opens and merges PRs by hand.
- Git "LF will be replaced by CRLF" warnings are harmless. The first commit is named "chunk 0" (pre-rule; left as is).
- Merged branches still exist locally and on GitHub.
- **Changing `EMBEDDING_DIMENSIONS` needs a new migration** and a re-index; a test catches a mismatch.
  Voyage (1024 dims) stays disabled at 1536. `pgvector` returns numpy arrays.
- **Repositories don't check that a parent row belongs to the same user.** Fix before auth.
- **`litellm` takes ~11 s to import**: lazy import; `LITELLM_LOCAL_MODEL_COST_MAP=True`.
- **LiteLLM wraps mid-stream errors in `MidStreamFallbackError`** (a ServiceUnavailableError) with
  the real error in `original_exception`. `map_provider_error` unwraps it and also maps by HTTP
  status (429, 401/403); logs show `type=... root=... status=...`. The free Gemini tier
  rate-limits quickly: after ~30 calls in a few minutes, wait before re-running the demo.
- **Rows created in one transaction share `now()`**: never order by `created_at` to find "newest".
- **The running app must import every model** (`app/db/session.py` imports `app.db.models`). Tests
  import everything, so they hid a missing import once: the first usage row failed on
  `agent_runs`. `tests/test_app_wiring.py` checks this in a fresh interpreter.
- **Under Starlette/anyio, cancellation hits every later `await`.** Writes after a client
  disconnect (usage row, partial reply, lock release) run inside `anyio.CancelScope(shield=True)`.
- Tests run Alembic in a separate thread (`env.py` calls `asyncio.run()`).
- **Every write endpoint needs a JSON body** (even `{}`), or `/docs` sends no Content-Type and
  gets 415 (fixed for the key test in PR #10; `tests/test_app_wiring.py` guards it).
- **Swagger's "Example Value" is not the real answer**; the real one is under "Server response".
- OpenAI: `auth_failed` = wrong or partial key; `rate_limited` on a tiny test = no credit.
- **What FakeProvider tests can't prove:** real summary quality, real token counts, real
  streaming/usage chunks from each provider. Only `scripts/switch_demo.py` with real keys does.

## Environment notes

- Windows 11, PowerShell 5.1 (Git Bash also available). Python 3.14; venv `backend\.venv`. Code must work on 3.12+.
- Docker container `mantleai-db-1`, image `pgvector/pgvector:pg16`, volume `pgdata`.
- `DATABASE_URL=postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/mantle` (local dev only); tests use `mantle_test`.
- API: `uvicorn app.main:app --reload` from `backend` → `http://127.0.0.1:8000` (`/health`, `/docs`).
- GitHub remote: `origin` → `MohammadAnas-07/MantleAI`, default branch `main`.

## Archive

- (empty)
