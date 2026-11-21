# CLAUDE.md

Rules for any AI tool (or person) that edits this repo.

**Read `docs/rules.md` and `docs/memory.md` before starting any task.**
**At the end of every task, update `docs/memory.md`.**

Mantle AI is a **software product**, a local, open-source workspace for working with multiple
LLMs. It is not an LLM. Background: `docs/idea.md`, `docs/architecture.md`, `docs/phases.md`.

## Stack

- Backend: Python 3.12+ (developed on 3.14), FastAPI, Pydantic v2, SQLAlchemy 2 async + asyncpg, Alembic
- Database: PostgreSQL 16 + pgvector in Docker, on `127.0.0.1:5433`
- LLMs: LiteLLM, only inside `modules/llm`. Agents: LangGraph is not used in v0.1 (see ADR 0004)
- Frontend: React 19 + Vite + TypeScript 5.9 (strict) + Tailwind 4, TanStack Query, react-router,
  Vitest + Testing Library + MSW, ESLint, Prettier. Design: `docs/design-app.md`
- Tooling: ruff (line length 100), pytest + pytest-asyncio, httpx

## Layout

```
backend/app/
  main.py      core/  db/  api/
  modules/     projects  conversations  llm  rag  workflow  teaching  execution
               each: router.py  schemas.py  models.py  service.py (public interface)
backend/tests/
frontend/src/   lib/api (client, SSE reader, generated schema.ts)  components/ui  layout
                hooks  features/{settings,projects,index,memory,conversations,context,activity}
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

Frontend (second terminal, from `frontend`):

```powershell
npm install
npm run dev                          # http://127.0.0.1:5173 (VITE_API_BASE_URL, see .env.example)
npm run typecheck; npm run lint; npm run format:check; npm run test; npm run build
npm run gen:api:check                # fails if src/lib/api/schema.ts is out of date
```

First-time setup is in `README.md`.

## Frontend rules (full list in docs/rules.md)

- TypeScript strict, **no `any`** (lint error). Use `unknown` and narrow it.
- API types come from the backend's OpenAPI schema: change an endpoint, run `npm run gen:api`
  and commit `openapi.json` and `schema.ts`. Hand-written types only for `dict` responses
  (`src/lib/api/types.ts`).
- All requests go through `src/lib/api/client.ts`; streams through `src/lib/api/sse.ts`.
- API keys never go into storage, URLs, logs or error messages; no prompts or message text in
  the console. Model output is rendered without raw HTML.

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
- docs/memory.md is updated in the same branch as the work, in its own commit, before the pull request is opened. Do not record PR numbers or merge commit hashes there. Do not create a separate branch just to update memory. Only a pure documentation catch-up that was missed may use its own docs/ branch.

## Branch hygiene

- One feature, one branch. Small fixes that belong to the feature go in that branch; a separate
  fix branch is only for something unrelated or urgent.
- Never create a branch just for memory, status or reports. `docs/memory.md` is updated in the
  feature branch.
- Only one Claude Code session works in a folder at a time.
- Merged branches are deleted with `git branch -d` (never `-D`).
- The user opens and merges pull requests.
