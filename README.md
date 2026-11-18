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
