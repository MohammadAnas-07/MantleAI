# Project memory

Working memory for any AI tool and for the developer. Read it before every task.

**Rules for this file**
- Update this file at the end of every task.
- Keep it under 150 lines.
- Never store secrets, passwords or API keys here.
- Move old items to the bottom section "Archive".

## Current status

Phase 1 has not started coding yet. The backend is a scaffold: FastAPI with `GET /health`, async
SQLAlchemy session, settings from `backend/.env`, and one test. PostgreSQL + pgvector runs in
Docker on `127.0.0.1:5433`. Product, architecture and process docs are written (`docs/`).
Dependencies have version ranges and a lock file (`chore/pin-dependencies`, committed, not yet
merged). Next is `feat/database-models`. First demo (model switching) target: 2026-12-17.
Last updated 2026-11-17.

## Done

- 2026-11-17: Project scaffold (FastAPI, `/health`, Docker Postgres, ruff, pytest), committed on `main` as `f0229e8`.
- 2026-11-17: `/health` database check gives up after 2 s (`1c82add`).
- 2026-11-17: Docker Postgres moved to host port 5433 (`74d4c68`).
- 2026-11-17: `docs/project-documentation` merged as PR #1: architecture, requirements, scope, data model, API, security, roadmap, ADRs 0001–0005, decisions D1–D10.
- 2026-11-17: `fix/bind-database-to-localhost` merged as PR #2: Postgres published only on 127.0.0.1; `127.0.0.1` in `DATABASE_URL`.
- 2026-11-17: `docs/product-and-process-docs` merged as PR #3: idea, PRD, rules, phases, this memory file; CLAUDE.md shortened; product decisions recorded.
- 2026-11-17: `chore/pin-dependencies`: compatible version ranges for every dependency in `backend/pyproject.toml`, exact versions in `backend/requirements.lock`, "Reproducible install" section in README (committed, not yet pushed or merged).

## In progress

- Nothing.

## Next

1. `feat/database-models`: Alembic setup, v0.1 tables, default local user.
2. `feat/llm-gateway`: encrypted keys, LiteLLM calls, usage records, fake provider.
3. `feat/model-switching`: conversations, streaming, rolling summary, switch. Ends Phase 1.

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

Full decision text: `docs/architecture.md` → Decisions.

## Known issues and gotchas

- **A PostgreSQL 17 Windows service (`postgresql-x64-17`) listens on 5432.** Using 5432 for Docker reaches the wrong database (`role "mantle" does not exist`). Keep 5433.
- **The first DB connection after a container (re)start can take over 2 s**, so `/health` may say `"down"` for a few seconds. Refresh after a short wait.
- **Docker Desktop is sometimes very slow or hangs** (`docker exec`, `docker compose up` timed out once). Retry with a longer wait.
- **Python/pytest startup is slow on this machine** (6–16 s for one test). It isn't a test problem.
- **`backend/requirements.lock` was made on Windows with Python 3.14.** A few platform-only packages (for example `colorama`) can differ elsewhere. When you add or change a dependency, regenerate the lock file with `python -m pip freeze --exclude-editable > requirements.lock`.
- **There is no LICENSE file yet**, although the project is open source.
- **`gh` (GitHub CLI) isn't installed, and the built-in browser isn't signed in to GitHub.** The developer opens and merges PRs by hand.
- Git prints "LF will be replaced by CRLF" warnings on commit; they are harmless.
- The first commit on `main` is named "chunk 0: project scaffold", from before the naming rule. It's left as-is because rewriting pushed history isn't worth it.
- Merged branches `docs/project-documentation` and `fix/bind-database-to-localhost` still exist locally and on GitHub.

## Environment notes

- Windows 11, PowerShell 5.1 (Git Bash is also available). Paths use backslashes in PowerShell.
- Python 3.14; the venv is `backend\.venv` (`.venv\Scripts\Activate.ps1`). The code must also work on 3.12 and 3.13.
- Docker Desktop must show "Engine running". Container `mantleai-db-1`, image `pgvector/pgvector:pg16`, volume `pgdata`.
- `DATABASE_URL=postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/mantle` (local dev only).
- API: `uvicorn app.main:app --reload` from `backend` → `http://127.0.0.1:8000` (`/health`, `/docs`).
- GitHub remote: `origin` → `MohammadAnas-07/MantleAI`, default branch `main`.

## Archive

- (empty)
