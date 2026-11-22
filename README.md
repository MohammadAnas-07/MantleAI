# Mantle AI

Mantle is a local, open-source workspace for building software with several LLMs. It is not an
LLM: it calls the providers you choose, with your own API keys.

When a model hits its limit mid-task, you copy the chat into another one and spend about 10
minutes explaining the project again. Mantle keeps the project's requirements, decisions, tasks,
a rolling conversation summary and the indexed code in a local database, so the next model picks
up where the last one stopped. It is for one developer on their own machine ([idea](docs/idea.md)).

## Status

Version 0.1 is not finished. One developer builds it. Works today, in the API and the web app:

- Projects, encrypted provider keys with a test call, and streaming chat.
- Model switching mid-conversation, with a preview. The old model is never called.
- Project memory (requirements, decisions, tasks), pinned into every prompt.
- Indexing a local folder, hybrid code search, and answers that cite `path:lines`.
- A project profile (languages, dependencies, commands) read from the files without a model.
- The workflow page: five stages with human approval, a gap finder, and Planner and Reviewer
  runs whose drafts are saved only when you approve them.

Planned, not built: teaching notes and the concepts list, a model-written project summary
(`feat/profile-summary`, deferred), sandboxed command execution, login and accounts, the landing
page, `GET /messages/{id}/context` and `GET /audit-events`. Order: [roadmap](docs/roadmap.md).

## How it works

One FastAPI process, split into modules, with PostgreSQL 16 and pgvector in Docker, and a React
app in the browser. Every model call goes through one gateway module (built on LiteLLM), which
logs it to a usage table. A context builder assembles each prompt from the system prompt, pinned
memory, the project profile, the rolling summary, retrieved code and recent messages, within the
target model's token budget. Details: [docs/architecture.md](docs/architecture.md).

## Quick start

You need Python 3.12 or newer, Docker Desktop (running), Node.js 22 or newer, and Git. Commands
are for Windows PowerShell; [docs/setup.md](docs/setup.md) explains each step and common errors.

```powershell
docker compose up -d                       # PostgreSQL on 127.0.0.1:5433
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env                # put the next line's output after MASTER_ENCRYPTION_KEY=
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
alembic upgrade head
python -m app.db.seed                      # default local user and model catalog
uvicorn app.main:app --reload              # http://127.0.0.1:8000, docs at /docs
```

Without the master key the API won't start; if you lose it, saved provider keys can't be read.
In a second terminal, run `cd frontend`, `npm install` and `npm run dev`, then open
<http://127.0.0.1:5173> and add a provider key in the settings. A free Google AI Studio key is
enough for chat and for indexing.

## Indexing a project

> Warning: indexing sends your code to your embedding provider. Every indexed file is split into
> segments and each one is sent to the provider of your embedding model (by default Google,
> `gemini/gemini-embedding-001`). Every chat message in an indexed project is sent there too, as
> the search query. Free tiers (for example the free Gemini API tier) may use what you send to
> train their models. Don't index code you are not allowed to share with that provider.

Mantle skips `.env*` files, keys and certificates, credential files, binaries, files over 1 MB,
anything `.gitignore` matches, and any file whose content looks like it holds a secret. This is a
safety net, not a guarantee (full list in [docs/security.md](docs/security.md)). A cost estimate
comes first, and indexing above `INDEX_COST_LIMIT_USD` (default $1.00) needs `force`. Each run
also rebuilds the project profile ([setup](docs/setup.md#the-project-profile)).

## Privacy and security

What leaves your machine, and when:

- Your messages and the prompt Mantle builds go to the chat model you picked, when you send.
- Indexed code, and each chat message in an indexed project, go to the embedding provider.
- The rolling summary is the only call you don't start yourself. It goes to the utility model,
  shows on its own line in the usage view, and can be turned off.
- "Test key" makes one tiny call to that provider.

Everything else stays in the local PostgreSQL volume. Provider keys are stored encrypted and never
returned or logged. Logs hold ids, counts and error codes, not prompts, replies or file contents.
Mantle never writes to your project folder and runs no shell commands. The API has no login and
answers only your own computer (unless `ALLOW_REMOTE_CLIENTS` is on); the database listens only
on `127.0.0.1`. Don't expose either on a network. Details: [docs/security.md](docs/security.md).

## Evaluation

No solid numbers yet. On 2026-11-18 the switch demo (`backend\scripts\switch_demo.py`) scored 5
of 5 decision questions after a switch from Gemini 3.8 Flash to Gemini 3.5 Flash Lite, in two runs
(all history verbatim; decisions only via the rolling summary). One provider, no saved results.

## Limits and known issues

- No CI: there is no `.github` workflow, so tests and linters run only by hand.
- No real-use evaluation of v0.1 yet: the 2-week trial in [docs/prd.md](docs/prd.md) hasn't
  started. The larger retrieval evaluation (25 questions on a real repository) stopped at the
  Gemini daily limit and has no result.
- Gemini 3.8 Flash times out at 120 seconds (`LLM_TIMEOUT_SECONDS`) in both chat and agent runs on
  this setup, so a lite model (Gemini 3.5 Flash Lite) is used. On it the Planner and Reviewer
  returned valid output, but that is one sample: agent output quality is not proven. Chat and
  switching have been run for real only on Gemini models.
- Some lists stop at a fixed size with no message that more exist: a conversation shows its first
  500 messages, the activity log its newest 200 calls, and the agent run and gap finder lists
  their newest 50 runs. The app reads at most 100 memory items per kind; the memory panel says
  "Showing X of Y", but a reference to a later item shows its id instead of its title. The built
  app is one 600 kB script (audit A-020; the `fix/list-limits-and-bundle` work is not done).
- Index and agent runs live in the server process; a restart (also `--reload`) stops them.
- No login, and repositories don't yet check that a parent row belongs to the user (to fix
  before auth). Don't run Mantle anywhere but your own machine.
- The teaching layer (teaching notes and the concepts list) and the model-written profile summary
  are not built.
- One Docker volume holds all data, with no automatic backup
  ([backup and restore](docs/setup.md#backup-and-restore)). No LICENSE file yet; MIT is planned.

## Tests and contributing

From `backend`: `pytest`, `ruff check .` and `ruff format --check .`. From `frontend`:
`npm run typecheck`, `npm run lint`, `npm run test` and `npm run build`. Tests need no API keys
and no network. pytest needs a `TEST_DATABASE_URL` database ending in `_test` (see setup).

Read [CLAUDE.md](CLAUDE.md) and [docs/rules.md](docs/rules.md) first. One roadmap item per
branch, named `type/short-topic` (`feat`, `fix`, `docs`, `chore`, `refactor`, `test`). Commits
are `type: short lowercase message`. Nobody commits to `main`; every change goes through a pull
request. Never commit a `.env` file.
