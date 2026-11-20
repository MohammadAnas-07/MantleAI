# Mantle AI

Mantle AI is a developer workspace for working with multiple LLMs.

This is **chunk 0**: the project skeleton only. There is one endpoint, `GET /health`, which tells you
whether the API is running and whether it can reach the database.

## Project layout

```
backend/    Python API (FastAPI). All Python commands are run from this folder.
frontend/   Placeholder. React + Vite + TypeScript + Tailwind come in a later chunk.
docs/       Project documents.
.vscode/    Editor settings and a debug configuration.
docker-compose.yml   Starts a local PostgreSQL database (with pgvector) in Docker.
```

## What you need installed

- Python 3.12 or newer (3.14 is fine)
- Docker Desktop (open it and wait until it says "Engine running")
- Git and VS Code

## First-time setup (Windows PowerShell)

Open PowerShell in the project folder (the folder that contains this README). In VS Code:
**Terminal → New Terminal**.

### 1. Go into the backend folder

```powershell
cd backend
```

All Python commands below run from `backend`.

### 2. Create a virtual environment

```powershell
python -m venv .venv
```

A virtual environment is a private folder (`backend\.venv`) that holds this project's Python
packages, so they don't mix with other projects. You only do this once.

### 3. Activate the virtual environment

```powershell
.venv\Scripts\Activate.ps1
```

When it works, your prompt starts with `(.venv)`. You must activate it every time you open a new
terminal.

If you get an error like *"running scripts is disabled on this system"*, run this once, then try
again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

This allows locally created scripts (like `Activate.ps1`) to run, for your user only.

### 4. Upgrade pip

```powershell
python -m pip install --upgrade pip
```

`pip` is Python's package installer. A recent version avoids install problems.

### 5. Install the project and its dev tools

```powershell
pip install -e ".[dev]"
```

- `-e` installs the project in "editable" mode: your code changes take effect without reinstalling.
- `.[dev]` also installs the developer tools: pytest (tests), httpx (HTTP client for tests) and ruff
  (linter and formatter).

#### Reproducible install

`pyproject.toml` allows a *range* of versions for each package, so `pip install -e ".[dev]"` may
pick newer versions on different days. `backend\requirements.lock` records the **exact** versions
that are known to work. To get exactly those, run this from `backend` with the venv active,
instead of step 5:

```powershell
pip install -r requirements.lock
pip install -e . --no-deps
```

The first command installs every package at its locked version (dev tools included). The second
installs Mantle itself in editable mode without letting pip change any versions.

Which one to use:

- **Normal development:** `pip install -e ".[dev]"` (step 5).
- **Something broke after an install, a fresh machine, or CI:** the two commands above.

When you change dependencies in `pyproject.toml`, install them, run the tests, and regenerate the
lock file:

```powershell
python -m pip freeze --exclude-editable > requirements.lock
```

The lock file was made on Windows with Python 3.14. On other systems a few platform-only packages
can differ (for example `colorama` is Windows-only).

### 6. Start the database

```powershell
cd ..
docker compose up -d
```

This starts PostgreSQL in the background (`-d`), using `docker-compose.yml`. The data is kept in a
Docker volume called `pgdata`, so it survives restarts. To stop it later: `docker compose down`.

The database is reachable only from your own computer, at **127.0.0.1, port 5433** (not the usual
5432). Other devices on your network cannot connect to it. Port 5433 avoids a clash if PostgreSQL
is also installed directly on Windows, which uses 5432.

### 7. Create the tables and the local user

Put a `MASTER_ENCRYPTION_KEY` in `backend\.env` first (see [Configuration](#configuration)). Then:

```powershell
cd backend
alembic upgrade head
python -m app.db.seed
```

`alembic upgrade head` creates every table and enables pgvector. `python -m app.db.seed` creates
the default local user and the default model catalog; running it again does nothing (and keeps
any model changes you made). To remove all tables:
`alembic downgrade base`.

### 8. Start the API server

```powershell
uvicorn app.main:app --reload
```

`--reload` restarts the server automatically when you save a file. Stop it with `Ctrl+C`.

### 9. Check it in your browser

- <http://127.0.0.1:8000/health> should show `{"status":"ok","database":"up"}`.
  If the database is not running you will see `"database":"down"`; the API still works.
- <http://127.0.0.1:8000/docs> shows interactive API documentation.

### 10. Run the tests and the linter

Open a second terminal (keep the server running in the first), then:

```powershell
cd backend
.venv\Scripts\Activate.ps1
pytest
ruff check .
```

Database tests use a separate database, `mantle_test`, which they create if it's missing; they
never touch `mantle`. If PostgreSQL is down, those tests are skipped and the rest still pass.
`ruff format .` reformats the code.

## The web app (frontend)

The workspace UI is in `frontend`. It needs Node.js 22 or newer (an LTS release) and the API
running (step 8). In a second PowerShell window, from the project folder:

```powershell
cd frontend
Copy-Item .env.example .env.local    # optional: only if the API is not on http://127.0.0.1:8000
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. The API only accepts this origin (`CORS_ALLOWED_ORIGINS`) and the
host names `localhost` and `127.0.0.1` (`ALLOWED_HOSTS`); open the app by one of those names.

Checks, from `frontend`:

```powershell
npm run typecheck
npm run lint
npm run format:check
npm run test
npm run build
npm run gen:api:check
```

`npm run gen:api` regenerates `src/lib/api/schema.ts` from the backend's OpenAPI schema (it runs
`backend\scripts\export_openapi.py` with `backend\.venv`, no server needed). Run it after
changing an endpoint and commit the result.

### The workflow page

Open a project and choose **Workflow and agents** in the explorer (or the link on the project
page). It has three parts:

- **Stages.** The five stages, the current one marked. For the stage you open you see its goal,
  the checklist (tick and untick), and what its gate still needs. Approve it when the gate is
  met; otherwise "Approve anyway" asks for a reason. Skip and reopen ask for a reason too.
  Every change is in the history. Mantle never moves a stage by itself.
- **Gap finder.** One model call on request, with the model you pick and your key. It lists
  missing steps, risks, technical debt and scalability concerns, with links to the memory items
  they mention. Past results stay.
- **Planner and Reviewer.** Pick a plan run (for a requirement from memory or one you type) or a
  review run, and a model. "Estimate cost" shows the tokens and the upper bound of the cost
  first (no model call); the run starts when you confirm. Above `AGENT_RUN_COST_LIMIT_USD` you
  confirm a second time. The run is polled until it ends and can be cancelled. When the plan is
  ready you choose items, edit them, and approve or reject; only then is anything saved (tasks
  as `todo`, decisions as `proposed`). Saved items show a "from agent run" badge in memory, and
  a proposed decision has Accept and Reject buttons.

Agent and gap finder calls show as "agent run" in the activity panel and the usage view.

## Switch demo (real models)

`backend\scripts\switch_demo.py` measures the Phase 1 success metric with **real, paid** calls.
It plays 5 decisions to model A, switches to model B, asks 5 questions about those decisions and
prints a score (pass = at least 4 of 5). The turns, questions and expected keywords are in
`backend\scripts\switch_demo.yaml`. First save a key for both providers
(`POST /api/v1/credentials`), then from `backend`:

```powershell
python scripts\switch_demo.py --model-a anthropic/claude-sonnet-5-5 --model-b openai/gpt-5.6
```

With only a free Google AI Studio (Gemini) key, use two Gemini models. Which models the free tier
includes changes over time; if one answers `rate_limited` or `provider_unavailable`, try another.

```powershell
python scripts\switch_demo.py --model-a gemini/gemini-3.8-flash --model-b gemini/gemini-3.5-flash-lite
```

New catalog models appear after `python -m app.db.seed` (existing models and keys stay as they are).

## Indexing a project

> **Warning: indexing sends your code to your embedding provider.** Every indexed file is split
> into segments and each one is sent to the provider of your embedding model (by default Google,
> `gemini/gemini-embedding-001`). Every chat message in an indexed project is sent there too, as
> the search query. Free tiers (for example the free Gemini API tier) may use what you send to
> train their models. Don't index code you are not allowed to share with that provider.

Mantle skips `.env*` files, keys and certificates (`*.pem`, `*.key`, `*.pfx`, `id_*`, ...),
`credentials*` and `secrets*` files, binaries, lock files, minified files, files over 1 MB, and
any file whose content looks like it holds a secret (private key headers, AWS, OpenAI, Google,
GitHub, Slack or Stripe keys). It also follows `.gitignore`. This is a safety net, not a
guarantee; see `docs/security.md`.

From `backend`, with the API running and a Google key saved (`POST /api/v1/credentials`):

```powershell
$p = Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/projects -ContentType application/json -Body '{"name": "My app", "root_path": "C:\\code\\my-app"}'
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/projects/$($p.id)/index/estimate" -ContentType application/json -Body '{}'
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/api/v1/projects/$($p.id)/index" -ContentType application/json -Body '{}'
```

The estimate shows the file count, segments, tokens and cost first. Indexing is refused above
`INDEX_COST_LIMIT_USD` (default $1.00) unless you send `{"force": true}`. Re-running only embeds
what changed. Turn code context off for one conversation with
`PATCH /api/v1/conversations/{id}` and `{"code_context_enabled": false}`.

`backend\scripts\eval_retrieval.py` indexes the sample project in `backend\tests\fixtures` with
your real key and prints recall@5 and MRR for vector, text and hybrid search.

## Configuration

Settings are read from `backend\.env`. This file is for your machine only and is **not** committed to
Git. `backend\.env.example` lists the same keys with safe example values and **is** committed. If you
ever lose `.env`, copy the example:

```powershell
Copy-Item backend\.env.example backend\.env
```

| Key | Meaning |
| --- | --- |
| `APP_ENV` | `development` for local work |
| `LOG_LEVEL` | How much logging to show (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `DATABASE_URL` | How to connect to PostgreSQL |
| `MASTER_ENCRYPTION_KEY` | **Required.** Fernet key that encrypts your provider API keys; the API won't start without it. Generate it with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. If you lose or change it, saved provider keys can't be read |
| `EMBEDDING_DIMENSIONS` | Dimension of the vector column (default 1536). Changing it needs a new migration and re-indexing |
| `CORS_ALLOWED_ORIGINS` | Browser origins that may call the API, as a JSON list (default the Vite dev server on `localhost` and `127.0.0.1`, port 5173). Never `*` |
| `ALLOWED_HOSTS` | Host names the API answers to, as a JSON list (default `localhost` and `127.0.0.1`, any port). Others get 400 `invalid_host` |
| `DEFAULT_EMBEDDING_MODEL` | Embedding model used when you haven't picked one (default `gemini/gemini-embedding-001`) |
| `INDEX_COST_LIMIT_USD` | Indexing is refused above this estimated cost unless `force` is sent (default `1.00`) |
| `EMBED_BATCH_DELAY_SECONDS` | Pause between embedding batches, for free tiers with low per-minute limits (default `1.0`) |
| `INDEX_MAX_FILE_BYTES`, `INDEX_MAX_FILES` | Skip files over this size and past this count (defaults 1 MB, 20000) |
| `INDEX_SENSITIVE_PATTERNS` | Extra file patterns never to index, as a JSON list in gitignore syntax, for example `["private/", "*.secret"]` |

All indexing and retrieval settings, with their defaults, are in `backend\app\core\config.py`.

## VS Code

- Install the extensions **Python** (Microsoft) and **Ruff** (Astral Software).
- `.vscode/settings.json` points VS Code at `backend\.venv\Scripts\python.exe`, formats Python with
  ruff on save, and enables pytest in the Testing panel (flask icon).
- To debug the API: **Run and Debug** panel → **Backend: FastAPI (uvicorn --reload)** → green play
  button. Breakpoints in your code will be hit.

## Common errors

| Problem | What it means | Fix |
| --- | --- | --- |
| `python : The term 'python' is not recognized` | Python is not on your PATH | Try `py` instead of `python`, or reinstall Python with **"Add python.exe to PATH"** ticked, then open a new terminal |
| VS Code shows import errors / uses the wrong Python | VS Code picked another interpreter | `Ctrl+Shift+P` → **Python: Select Interpreter** → choose `backend\.venv\Scripts\python.exe`. Make sure you ran steps 2 and 5 first |
| `docker compose` fails with *"cannot connect to the Docker daemon"* / pipe error | Docker Desktop is not running | Start Docker Desktop, wait for "Engine running", then run `docker compose up -d` again |
| `/health` says `"database":"down"` | The database container is not running or not ready | Run `docker compose ps` from the project folder; if `db` is missing, run `docker compose up -d` |
| Port already in use (8000 or 5433) | Another program is using that port | For the API: `uvicorn app.main:app --reload --port 8001`. For the database: pick another free port and change it in both `docker-compose.yml` (`"127.0.0.1:5433:5432"`) and `DATABASE_URL` in `backend\.env` |
| `/health` says `"database":"down"` and the log shows `role "mantle" does not exist` | The app reached a different PostgreSQL (e.g. one installed on Windows), not the Docker one | Check that `DATABASE_URL` uses the same port as `docker-compose.yml` (5433) |
| `ModuleNotFoundError: No module named 'app'` | Command run from the wrong folder or venv not active | `cd backend`, activate the venv (step 3), and run step 5 if you haven't |
