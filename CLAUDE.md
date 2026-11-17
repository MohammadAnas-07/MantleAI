# CLAUDE.md

Working rules for any AI tool (or person) that edits this repo. Read this first, then
`docs/architecture.md` and `docs/mvp-scope.md`.

Mantle AI is a **software product**, a developer workspace for working with multiple LLMs. It is
not an LLM.

## Tech stack

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12+ (developed on 3.14), FastAPI, Pydantic v2, pydantic-settings, AsyncIO |
| Database | PostgreSQL 16 + pgvector (Docker image `pgvector/pgvector:pg16`), SQLAlchemy 2 async + asyncpg, Alembic |
| LLM access | LiteLLM Python SDK, called **only** from the `llm` module |
| Agents | LangGraph, **only** inside the `workflow` module |
| Frontend | React + Vite + TypeScript + Tailwind (not added yet) |
| Tooling | ruff (lint + format, line length 100), pytest + pytest-asyncio, httpx |

## Folder structure

```
backend/
  app/
    main.py            FastAPI app, mounts each module's router
    core/              config, logging, security helpers (shared, no business logic)
    db/                engine, session, Alembic base
    api/               API-wide pieces (error handlers, dependencies)
    modules/
      projects/        projects + project memory (requirements, decisions, tasks)
      conversations/   conversations, messages, context building, model switching
      llm/             LLM gateway: provider keys, model catalog, LiteLLM calls, usage
      rag/             file indexing, chunks, embeddings, retrieval
      workflow/        workflow stages, approvals, Planner and Reviewer agents
      teaching/        teaching notes
      execution/       sandboxed execution (Later; empty in v0.1)
  tests/
frontend/              React app (later)
docs/                  architecture, requirements, ADRs (docs/adr/)
docker-compose.yml     local PostgreSQL only
```

Each module uses the same files as it grows:

- `router.py`: FastAPI routes, thin. Parses input, calls the service, returns schemas.
- `schemas.py`: Pydantic request and response models.
- `models.py`: SQLAlchemy tables owned by this module.
- `service.py`: the module's **public interface**. Other modules may import only from here.

## Coding standards

- Type hints on every function. `async def` for anything that does I/O.
- Modules talk to each other only through `service.py` functions. Never import another module's
  `models.py` or `router.py`, and never query another module's tables directly.
- Only `modules/llm` imports `litellm`. Only `modules/workflow` imports `langgraph`.
- Configuration comes from `app.core.config.settings`. Never read `os.environ` elsewhere.
- Use `logging.getLogger(__name__)`. Never `print`.
- Validate all external input with Pydantic at the API edge.
- Keep functions small. Prefer plain functions over classes unless there is state to hold.
- Every change ships with tests. Run `ruff format .` before committing.

## How to run (PowerShell, from the repo root)

First-time setup is in `README.md`. Daily commands:

```powershell
docker compose up -d                 # start PostgreSQL (host port 5433)
cd backend
.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload        # API on http://127.0.0.1:8000, docs at /docs
```

Tests and lint, from `backend` with the venv active:

```powershell
pytest
ruff check .
ruff format --check .
```

## Rules

- **Modular monolith.** One FastAPI app and one database. No microservices.
- **No LangChain in core code.** Do not import `langchain` or `langchain_*` anywhere. LangGraph is
  allowed only inside `modules/workflow` (see `docs/adr/0004-langgraph-selective.md`).
- **No secrets in code or logs.** API keys live encrypted in the database. Never log prompts,
  keys, `Authorization` headers or file contents at INFO or above.
- **Tests must not need real API keys or network access.** Use the gateway's fake provider or
  LiteLLM's `mock_response`. A test that needs PostgreSQL must be marked `@pytest.mark.db` and
  skip cleanly when the database is not running.
- **One piece of work at a time.** Each task maps to one roadmap item and one branch. Do not mix
  in unrelated fixes; note them for a separate branch.

## What not to do

- Do not add anything listed as "Out" in `docs/mvp-scope.md` (Redis, queues, auth, Monaco, GitHub
  integration, code execution, reranker, extra agents) unless the task says so.
- Do not let any LLM or agent run shell commands, write files, or call tools that change state
  without explicit human approval.
- Do not send whole projects to an LLM. Use retrieval and the context budget.
- Do not add a dependency without saying why in the PR description.
- Do not apply `docs/design-landing.md` to the app UI. It is for the marketing landing page only.
- Do not edit `.env`, and do not change generated migrations after they have been merged.

## Definition of done

A task is done when all of these are true:

1. It does what its roadmap item says, and nothing more.
2. `pytest`, `ruff check .` and `ruff format --check .` pass in `backend`.
3. New behaviour has tests. The tests run without API keys or network access.
4. Database changes come with an Alembic migration that upgrades and downgrades.
5. Docs are updated if behaviour, API or data model changed (`docs/api-outline.md`,
   `docs/data-model.md`, `README.md`).
6. No secrets in the diff, and `git status` shows no `.env`.
7. The work is committed on its own branch with a conventional message.

## Git conventions

- **Branch names:** `type/short-topic`, for example `feat/llm-gateway` or `fix/health-timeout`.
  Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`.
- **Commit messages:** `type: short lowercase message`, for example
  `feat: add provider key storage`.
- One topic per branch. One roadmap item per branch.
- Nobody commits directly to `main`. All changes go through a pull request.
- Never commit `.env`. Only `backend/.env.example` is tracked.
- Never use the word "chunk" in branch names, commit messages or PR titles. (Inside code and docs
  it is fine when it means a RAG text chunk.)
