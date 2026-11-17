# CLAUDE.md

Rules for any AI tool (or person) that edits this repo.

**Read `docs/rules.md` and `docs/memory.md` before starting any task.**
**At the end of every task, update `docs/memory.md`.**

Mantle AI is a **software product**, a local, open-source workspace for working with multiple
LLMs. It is not an LLM. Background: `docs/idea.md`, `docs/architecture.md`, `docs/phases.md`.

## Stack

- Backend: Python 3.12+ (developed on 3.14), FastAPI, Pydantic v2, SQLAlchemy 2 async + asyncpg, Alembic
- Database: PostgreSQL 16 + pgvector in Docker, on `127.0.0.1:5433`
- LLMs: LiteLLM, only inside `modules/llm`. Agents: LangGraph, only inside `modules/workflow`
- Frontend (later): React + Vite + TypeScript + Tailwind
- Tooling: ruff (line length 100), pytest + pytest-asyncio, httpx

## Layout

```
backend/app/
  main.py      core/  db/  api/
  modules/     projects  conversations  llm  rag  workflow  teaching  execution
               each: router.py  schemas.py  models.py  service.py (public interface)
backend/tests/
docs/          architecture, rules, memory, phases, ADRs (docs/adr/)
```

## Run (PowerShell)

```powershell
docker compose up -d                 # PostgreSQL on 127.0.0.1:5433
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload        # http://127.0.0.1:8000, docs at /docs
pytest
ruff check .
ruff format --check .
```

First-time setup is in `README.md`.

## Core rules (full list in docs/rules.md)

- **Modular monolith.** One FastAPI app, one database, no microservices.
- **We never import `langchain*`; only `langgraph`,** and only in `modules/workflow`.
- Modules call each other only through `service.py`. Only `llm` imports `litellm`; only `rag` reads project files.
- **No secrets in code or logs.** Keys are encrypted in the database and never returned or logged.
- **Tests never need real API keys** or network access.
- **Any LLM call the user did not directly ask for must be logged, visible, and possible to turn off.**
- Every user-data table has `user_id`, and every query filters by it.
- No LLM output changes state without a human action. No shell execution in v0.1.
- **One piece of work at a time:** one roadmap item per branch.

## Don't

- Don't build anything listed as "Out" in `docs/mvp-scope.md`.
- Don't apply `docs/design-landing.md` to the app UI (it's for the landing page only).
- Don't add a dependency without a reason in the PR.
- Don't edit `.env` or a merged migration.
- Don't change `docs/architecture.md`, `docs/mvp-scope.md` or an ADR silently; list the conflict instead.

## Definition of done

1. It does what its roadmap item says, and nothing more.
2. `pytest`, `ruff check .` and `ruff format --check .` pass.
3. New behaviour has tests that run without API keys.
4. Schema changes have a migration that upgrades and downgrades.
5. Affected docs and `docs/memory.md` are updated.
6. `git status` shows no `.env`, and the work is committed on its own branch.

## Git conventions

- Branches: `type/short-topic` (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`).
- Commits: `type: short lowercase message`.
- One topic per branch. Nobody commits directly to `main`.
- Never commit `.env`.
- Never use the word "chunk" in branch names, commit messages or PR titles.
