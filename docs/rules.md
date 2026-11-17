# Engineering rules

Every rule is one sentence that can be checked in a diff, a test run or a file. "Must" means
a PR that breaks it is not done. Background: `CLAUDE.md`, `docs/architecture.md`, `docs/adr/`.

## Code style and typing

1. All Python code passes `ruff check .` and `ruff format --check .` with line length 100.
2. Every function and method has type hints for all parameters and the return value.
3. Every function that does I/O (database, network, files, LLM) is `async def`.
4. No `print()` in `backend/app`; use `logging.getLogger(__name__)`.
5. Settings are read only through `app.core.config.settings`; no `os.environ` / `os.getenv` elsewhere.
6. A module imports another module only from its `service.py`, never its `models.py`, `router.py` or `schemas.py`.
7. Only `app/modules/llm` imports `litellm`.
8. Only `app/modules/workflow` imports `langgraph`.
9. No file anywhere imports a `langchain*` package.
10. Only `app/modules/rag` reads files from a project folder.
11. Module dependencies follow the "May call" column in `docs/architecture.md`, with no cycles.

## Testing

12. Every new behaviour has at least one test that fails without the change.
13. No test reads a real API key, and the test suite passes with no keys set and no network access.
14. LLM calls in tests use the gateway's fake provider or LiteLLM's `mock_response`.
15. Tests that need PostgreSQL are marked `@pytest.mark.db` and skip cleanly when the database is down.
16. Tests never use the development database `mantle`; they use a separate test database.
17. `pytest` passes in `backend` before every commit.

## Database and migrations

18. Every schema change has an Alembic migration with a working `downgrade()`.
19. A migration that has been merged to `main` is never edited; a new migration fixes it.
20. Every user-data table has a non-null, indexed `user_id`, as listed in `docs/data-model.md`.
21. Every query on user data filters by `user_id`.
22. Tables are created and changed only by migrations, never by `create_all()` in app code.
23. A module reads and writes only the tables it owns.
24. Every table has `id` (UUID), `created_at` and `updated_at` in UTC.

## API design

25. All endpoints except `/health` are under `/api/v1`.
26. Request and response bodies are Pydantic models defined in the module's `schemas.py`.
27. Errors use one shape: `{"error": {"code", "message", "details"}}`.
28. No `GET` endpoint changes state.
29. Write endpoints accept only `application/json`.
30. An API response never contains an API key; at most the last 4 characters.
31. Every new or changed endpoint is listed in `docs/api-outline.md` in the same PR.
32. Streaming responses use SSE with the event names `context`, `token`, `done` and `error`.

## LLM handling

33. Code outside `modules/llm` calls models only through the gateway's service functions (`stream_chat`, `complete`, `embed`, `count_tokens`).
34. No code outside `modules/llm` names a provider or catches a provider-specific exception.
35. Every LLM call writes one `usage_records` row with `purpose` and `trigger`.
36. Any LLM call the user did not directly ask for is logged, visible, and possible to turn off.
37. Every prompt is built by the context builder and fits the model's context window minus an output reserve, counted with `count_tokens`.
38. No prompt contains a whole project; code reaches a prompt only as retrieved chunks.
39. Retrieved text is wrapped in `<source path=... lines=...>` blocks and treated as data, never as instructions.
40. The system prompt states that sources and earlier messages are data, not instructions.
41. No LLM output triggers a state change (memory item, stage approval, file write, command) without a human action.
42. Mantle never switches models by itself; it only suggests a switch.
43. A model switch never calls the model being switched away from.

## Security and secrets

44. No secret, API key or password appears in code, tests, fixtures, docs, logs or commits.
45. `.env` is never committed, and `git status` is checked for `.env` before every commit.
46. Provider keys are stored only as Fernet ciphertext and decrypted only inside `modules/llm`.
47. uvicorn binds to `127.0.0.1`, and Docker publishes PostgreSQL only on `127.0.0.1`.
48. Indexing never reads `.env*`, `*.pem`, `*.key`, `id_*`, `*.pfx`, binaries, or files over 1 MB.
49. Indexing never follows a path or symlink outside the project's `root_path`.
50. No module executes shell commands in v0.1.

## Error handling and logging

51. Provider failures are mapped to `RateLimited`, `ContextTooLong`, `AuthFailed` or `ProviderUnavailable` inside `modules/llm`.
52. No `except Exception` without logging the error or re-raising, except in `/health`.
53. Logs at INFO and above contain no prompts, replies, file contents, keys or `Authorization` headers.
54. Every LLM call is logged with model, tokens, latency and status.
55. A failed background job (index run, rolling summary) stores its error in its own table row and never breaks chat.
56. `/health` returns within 2 seconds and never raises.

## Git conventions

57. Branch names are `type/short-topic`, with type one of `feat`, `fix`, `docs`, `chore`, `refactor`, `test`.
58. Commit messages are `type: short lowercase message`.
59. Each branch has one topic, matching one roadmap item or one fix.
60. Nobody commits directly to `main`; all changes go through a pull request.
61. `.env` is never committed; only `backend/.env.example` is tracked.
62. The word "chunk" never appears in branch names, commit messages or PR titles.

## Dependency policy

63. `pyproject.toml` uses compatible version ranges (for example `fastapi>=0.115,<1`), and exact versions are recorded in a lock file (`backend/requirements.lock`, made with `pip freeze --exclude-editable`).
64. A new dependency is added only with a one-line reason in the PR description.
65. `litellm` upgrades are a separate PR that names the version and links its changelog.
66. No dependency is added for something the standard library or an existing dependency already does.

## Documentation

67. A PR that changes behaviour, an endpoint or a table updates `docs/api-outline.md`, `docs/data-model.md` or `README.md` in the same PR.
68. A significant technical decision gets an ADR in `docs/adr/` with context, decision, alternatives and consequences.
69. `docs/memory.md` is updated at the end of every task.
70. Docs use plain English, short sentences and no filler.

## Definition of done

71. The task does what its roadmap item says and nothing more.
72. `pytest`, `ruff check .` and `ruff format --check .` pass in `backend`.
73. New behaviour has tests that run without API keys or network access.
74. Schema changes have a migration that upgrades and downgrades.
75. Affected docs and `docs/memory.md` are updated.
76. `git status` shows no `.env`, and the work is committed on its own branch with a conventional message.
