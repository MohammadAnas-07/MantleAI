# Project memory

Working memory for any AI tool and for the developer. Read it before every task.

**Rules for this file**
- Update this file at the end of every task.
- Keep it under 150 lines.
- Never store secrets, passwords or API keys here.
- Move old items to the bottom section "Archive".

## Current status

Phase 1 is in progress. The database layer is merged (PR #5). The LLM gateway is built on
`feat/llm-gateway` (committed, not pushed or merged): LiteLLM backend, FakeProvider, typed errors,
usage records, model catalog, `/api/v1` foundation and the llm endpoints, 96 tests. After it
merges: run `alembic upgrade head` (migration `0002`) and `python -m app.db.seed` (adds the model
catalog) on the dev database. Next is `feat/model-switching`.
First demo (model switching) target: 2026-12-17.
Last updated 2026-11-18.

## Done

- 2026-11-17: Project scaffold (FastAPI, `/health`, Docker Postgres, ruff, pytest), committed on `main` as `f0229e8`.
- 2026-11-17: `/health` database check gives up after 2 s (`1c82add`).
- 2026-11-17: Docker Postgres moved to host port 5433 (`74d4c68`).
- 2026-11-17: `docs/project-documentation` merged as PR #1: architecture, requirements, scope, data model, API, security, roadmap, ADRs 0001–0005, decisions D1–D10.
- 2026-11-17: `fix/bind-database-to-localhost` merged as PR #2: Postgres published only on 127.0.0.1; `127.0.0.1` in `DATABASE_URL`.
- 2026-11-17: `docs/product-and-process-docs` merged as PR #3: idea, PRD, rules, phases, this memory file; CLAUDE.md shortened; product decisions recorded.
- 2026-11-17: `chore/pin-dependencies` merged as PR #4: compatible version ranges for every dependency in `backend/pyproject.toml`, exact versions in `backend/requirements.lock`, "Reproducible install" section in README.
- 2026-11-17: `feat/database-models` merged as PR #5 (`758e897`): models for every v0.1 table in each module's `models.py`
  (`users`, `audit_events` in `app/core/models.py`), shared base + naming convention in
  `app/db/base.py`, async Alembic (`backend/alembic`, migration `0001`), generic repositories
  (`app/db/repository.py`) plus one per table in `modules/<m>/repository.py`, Fernet helper
  `modules/llm/crypto.py`, seed `python -m app.db.seed`, tests on `mantle_test`. ExecutionRun not
  created (Later). `pgvector` added as a dependency.
- 2026-11-18: `feat/llm-gateway` (not merged yet): `modules/llm/gateway.py` (`stream_chat`,
  `complete`, `embed`, `count_tokens`, `test_credential`; one usage row per call, also on error
  and cancel), `litellm_backend.py` (only file importing litellm; lazy import), `fake.py`
  (FakeProvider with call log), typed errors in `errors.py`, catalog in `catalog.py` (seeded),
  migration `0002` (`model_configs.supports_tools`), `app/api/` (router, `get_db`,
  `get_current_user_id`, error shape, JSON-only middleware, `/me`), llm endpoints, key-masking log
  filter. `litellm>=1.110.0,<1.111` added.

## In progress

- Nothing.

## Next

1. Merge `feat/llm-gateway`.
2. `feat/model-switching`: the user's brief of 2026-11-18 (ContextBuilder with prompts/ files and a
   10% safety margin, incremental rolling summary with a per-conversation lock, conversation and
   switch endpoints, SSE, `backend/scripts/switch_demo.py` + YAML). Decided for it on 2026-11-18:
   SSE events are `message_start`, `delta`, `message_end`, `error` (update rule #32 and
   api-outline); usage names stay as in data-model (`chat`+`user`, `rolling_summary`+`background`,
   `switch_summary`+`user`); switching is `POST /conversations/{id}/switch-model`, the handoff note
   goes on ContextHandoff (new JSON column), partial replies are saved as status `cancelled`.
   When background summaries are off, the switch-time summary is written by the NEW model.
   Ends Phase 1.

After that, `feat/project-memory` is Phase 2.

## Decisions

| Date | Decision | Reason | ADR |
| --- | --- | --- | --- |
| 2026-11-17 | Modular monolith | One developer, one user; extract services only when needed | [0001](adr/0001-modular-monolith.md) |
| 2026-11-17 | PostgreSQL + pgvector for data and vectors | One system, joins with project data | [0002](adr/0002-postgres-pgvector.md) |
| 2026-11-17 | LiteLLM behind our own gateway | Many providers, one interface; core feature is switching | [0003](adr/0003-litellm-gateway.md) |
| 2026-11-17 | LangGraph only in `workflow`; never import `langchain*`; skip LangGraph if plain Python is enough | Keep core architecture ours | [0004](adr/0004-langgraph-selective.md) |
| 2026-11-17 | Local-first, one default user, `user_id` on all user data | Ship core features first; easy path to auth | [0005](adr/0005-local-first-single-user.md) |
| 2026-11-17 | Docker Postgres on host port 5433 | Windows PostgreSQL 17 service already uses 5432 | — |
| 2026-11-17 | `/health` DB check limited to 2 s | Answer fast when the DB is down | — |
| 2026-11-17 | Embeddings via small OpenAI or Voyage model; user needs an embeddings-capable key | No local model in v0.1 (D2) | 0002, 0003 |
| 2026-11-17 | Utility model + background rolling summary; switch never calls the old model (D3) | Switching must work when the old model is failing | 0003 |
| 2026-11-17 | Unrequested LLM calls must be logged, visible and possible to turn off (D10) | Background calls cost the user money | 0003 |
| 2026-11-17 | Concepts list is rule-based (YAML + project profile), no LLM (D10) | No hidden cost | — |
| 2026-11-17 | Open source, unpaid; users pay only their own provider costs | Author's choice | — |
| 2026-11-17 | License: MIT; no LICENSE file until the repo is public | Simple, widely known; fits an unpaid open-source project | — |
| 2026-11-17 | Not a hosted service in v0.1; revisit after the first demo | Keep v0.1 small; `user_id` keeps hosting possible | 0005 |
| 2026-11-17 | Work in 6 phases; Phase 1 ends with model switching working | Prove the core feature first | `docs/phases.md` |
| 2026-11-17 | Split workflow and memory: `feat/project-memory` right after model switching; `feat/workflow-and-agents` later | Memory is the differentiator and cheaper than RAG | `docs/phases.md` |
| 2026-11-17 | Success = 10 switches in 2 weeks, each < 1 min, no re-explaining, and ≥ 4 of 5 decision questions correct | Makes the metric testable | `docs/prd.md` |
| 2026-11-17 | Version ranges in `pyproject.toml` + exact versions in `requirements.lock` | Reproducible installs without over-pinning | `docs/rules.md` #63 |
| 2026-11-17 | 3 evenings per week | Basis for all phase dates | `docs/phases.md` |
| 2026-11-17 | Messages store provider-neutral content parts (JSON: text, tool_call, tool_result) + `input_tokens`/`output_tokens` | Ready for tools and any provider | `docs/data-model.md` |
| 2026-11-17 | Default local user (fixed id `...0001`) is created by the seed script, not a migration | Migrations hold schema only | ADR 0005 (amended) |
| 2026-11-17 | Table names from `docs/data-model.md` (`provider_credentials`; usage `purpose` + `trigger`) | data-model.md is the source of truth | — |
| 2026-11-17 | Fernet helper built in `feat/database-models`, not `feat/llm-gateway` | Credentials table needs it now | `docs/roadmap.md` |
| 2026-11-17 | Enums are VARCHAR(32), no PG enum types or CHECK constraints | Adding a value needs no migration | `docs/data-model.md` |
| 2026-11-17 | SET NULL FKs are DEFERRABLE INITIALLY DEFERRED | Project delete cascades must not trip FK checks mid-cascade | `docs/data-model.md` |
| 2026-11-17 | Usage records keep rows on project/conversation delete (SET NULL) | Cost history stays complete | `docs/data-model.md` |
| 2026-11-18 | `feat/llm-gateway` before `feat/model-switching`, on its own branch | Model switching needs the gateway; one topic per branch | `docs/roadmap.md` |
| 2026-11-18 | Gateway backends: `LiteLLMBackend` (real) and `FakeProvider` (tests), chosen by the `get_gateway` dependency | Tests never need keys or network | 0003 |
| 2026-11-18 | Default model catalog hardcoded from LiteLLM 1.110.0 data, seeded with `ON CONFLICT DO NOTHING` | Seeding works offline and keeps user changes | — |
| 2026-11-18 | Usage purpose `key_test` for the "test key" call | Every LLM call writes a usage row | `docs/data-model.md` |
| 2026-11-18 | Write requests must be JSON (415 otherwise), via a pure ASGI middleware | security.md #7; pure ASGI keeps SSE working | `docs/security.md` |
| 2026-11-17 | The API refuses to start without a valid `MASTER_ENCRYPTION_KEY` | Fail fast instead of failing on first key use | `docs/security.md` |

Full decision text: `docs/architecture.md` → Decisions.

## Known issues and gotchas

- **A PostgreSQL 17 Windows service (`postgresql-x64-17`) listens on 5432.** Using 5432 for Docker reaches the wrong database (`role "mantle" does not exist`). Keep 5433.
- **The first DB connection after a container (re)start can take over 2 s**, so `/health` may say `"down"` for a few seconds. Refresh after a short wait.
- **Docker Desktop is sometimes very slow or hangs** (`docker exec`, `docker compose up` timed out once). Retry with a longer wait.
- **The database container can stop by itself** (`Exited (255)`, seen once after Docker Desktop slept or restarted). Then `alembic` fails with `WinError 1225 ... refused the network connection`. Check `docker compose ps` and run `docker compose up -d` from the project folder.
- **A Fernet key is 44 characters and ends with `=`.** Copying it without the last `=` gives "not a valid Fernet key" at startup.
- **Commands for PowerShell don't work in Git Bash** (`.venv\Scripts\Activate.ps1`). In Git Bash use `source .venv/Scripts/activate`.
- **Python/pytest startup is slow on this machine** (6–16 s for one test). It isn't a test problem.
- **`backend/requirements.lock` was made on Windows with Python 3.14.** A few platform-only packages (for example `colorama`) can differ elsewhere. When you add or change a dependency, regenerate the lock file with `python -m pip freeze --exclude-editable > requirements.lock`.
- **There is no LICENSE file yet**, although the project is open source.
- **`gh` (GitHub CLI) isn't installed, and the built-in browser isn't signed in to GitHub.** The developer opens and merges PRs by hand.
- Git prints "LF will be replaced by CRLF" warnings on commit; they are harmless.
- The first commit on `main` is named "chunk 0: project scaffold", from before the naming rule. It's left as-is because rewriting pushed history isn't worth it.
- Merged branches `docs/project-documentation`, `fix/bind-database-to-localhost`, `docs/product-and-process-docs`, `chore/pin-dependencies` and `feat/database-models` still exist locally and on GitHub.

- **Changing `EMBEDDING_DIMENSIONS` needs a new migration** (migration `0001` froze 1536) and a
  re-index. `tests/test_migrations.py::test_embedding_column_matches_setting` catches a mismatch.
- **The API won't start until `MASTER_ENCRYPTION_KEY` is set in `backend/.env`.** Generate with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- **Repositories don't check that a parent row belongs to the same user** (for example a message
  pointing at another user's conversation). Only one user exists in v0.1; fix before auth, with
  composite FKs `(parent_id, user_id)` or service-level checks.
- Tests run Alembic in a separate thread, because `alembic/env.py` calls `asyncio.run()`.
- **`litellm` takes about 11 s to import.** It's imported lazily on the first real call;
  `LITELLM_LOCAL_MODEL_COST_MAP=True` stops it downloading model data.
- **Rows created in one transaction share `now()`,** so "newest" by `created_at` is a tie in tests
  (and in any single request). Tests age rows with SQL. Model switching should order summaries by
  the message sequence they cover, not by time.
- Voyage embeddings are 1024-dimensional, so Voyage stays disabled while `EMBEDDING_DIMENSIONS` is
  1536.
- `pgvector` returns embeddings as numpy arrays, not lists (numpy comes in with `pgvector`).

## Environment notes

- Windows 11, PowerShell 5.1 (Git Bash is also available). Paths use backslashes in PowerShell.
- Python 3.14; the venv is `backend\.venv` (`.venv\Scripts\Activate.ps1`). The code must also work on 3.12 and 3.13.
- Docker Desktop must show "Engine running". Container `mantleai-db-1`, image `pgvector/pgvector:pg16`, volume `pgdata`.
- `DATABASE_URL=postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/mantle` (local dev only).
- API: `uvicorn app.main:app --reload` from `backend` → `http://127.0.0.1:8000` (`/health`, `/docs`).
- GitHub remote: `origin` → `MohammadAnas-07/MantleAI`, default branch `main`.

## Archive

- (empty)
