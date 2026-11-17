# API outline

REST + JSON, under `/api/v1`, except `/health`. Streaming uses server-sent events (SSE). There is
no auth in v0.1: every request runs as the default local user, and every query filters by that
user's `user_id` (see `docs/security.md`). Every write request must send
`Content-Type: application/json`.

Errors look the same everywhere: `{"error": {"code": "rate_limited", "message": "...", "details": {}}}`.

## System

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | API status and database `up`/`down` |
| GET | `/api/v1/me` | The current user (in v0.1, always the default local user) |
| GET | `/api/v1/audit-events` | List recent audit events (filter by type) |

## LLM gateway (`llm`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/providers` | List supported providers, whether a key is set, and whether the provider can do embeddings |
| GET | `/api/v1/credentials` | List saved keys (label, provider, last 4 characters only) |
| POST | `/api/v1/credentials` | Save a key `{provider, label, api_key}` (encrypted, never returned) |
| POST | `/api/v1/credentials/{id}/test` | Make a tiny test call with this key |
| DELETE | `/api/v1/credentials/{id}` | Delete a key |
| GET | `/api/v1/models` | List models (`kind`, context window, enabled) |
| PATCH | `/api/v1/models/{id}` | Enable or disable a model, override its context window |
| GET | `/api/v1/settings/models` | The utility model (null = the active model) and the embedding model |
| PATCH | `/api/v1/settings/models` | Change the utility model or the embedding model (changing the embedding model means re-indexing) |
| GET | `/api/v1/usage` | Token and cost totals (filter by project, model, date) |

## Projects and memory (`projects`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/projects` | List projects |
| POST | `/api/v1/projects` | Create a project `{name, description, root_path}` |
| GET | `/api/v1/projects/{id}` | Get one project |
| PATCH | `/api/v1/projects/{id}` | Update name, description, path, default model; archive |
| DELETE | `/api/v1/projects/{id}` | Delete a project and all its data |
| GET | `/api/v1/projects/{id}/memory` | List memory items (filter by `kind`, `status`) |
| POST | `/api/v1/projects/{id}/memory` | Add a memory item by hand |
| PATCH | `/api/v1/memory/{item_id}` | Edit an item or change its status |
| POST | `/api/v1/memory/{item_id}/approve` | Approve a `proposed` item (makes it `active`) |
| POST | `/api/v1/memory/{item_id}/reject` | Reject a `proposed` item |
| DELETE | `/api/v1/memory/{item_id}` | Delete an item |

## Conversations and model switching (`conversations`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/projects/{id}/conversations` | List the project's conversations |
| POST | `/api/v1/projects/{id}/conversations` | Create one `{title, model_id}` |
| GET | `/api/v1/conversations/{id}` | Get a conversation and its current model |
| PATCH | `/api/v1/conversations/{id}` | Rename |
| DELETE | `/api/v1/conversations/{id}` | Delete |
| GET | `/api/v1/conversations/{id}/messages` | List messages (paged) |
| POST | `/api/v1/conversations/{id}/messages` | Send a message. The response is an SSE stream: `context`, `token`, `done`, `error` |
| POST | `/api/v1/messages/{id}/cancel` | Stop a reply that is still streaming |
| GET | `/api/v1/messages/{id}/context` | Sources and memory items used for this reply |
| GET | `/api/v1/conversations/{id}/summary` | The current rolling summary and which messages it covers |
| GET | `/api/v1/conversations/{id}/handoff-preview?model_id=` | What would carry over to that model (summary, raw messages kept, token counts) |
| POST | `/api/v1/conversations/{id}/switch-model` | Switch `{model_id, reason}`, creating a ContextHandoff (never calls the old model) |
| GET | `/api/v1/conversations/{id}/handoffs` | History of model switches |

## RAG (`rag`)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/projects/{id}/index` | Start (re-)indexing `root_path`. Returns 202 `{run_id}`, or 422 if no embeddings-capable key or embedding model is set |
| GET | `/api/v1/projects/{id}/index-runs` | List index runs |
| GET | `/api/v1/index-runs/{run_id}` | Progress and result of one run |
| POST | `/api/v1/index-runs/{run_id}/cancel` | Stop a running index |
| GET | `/api/v1/projects/{id}/documents` | List indexed files |
| POST | `/api/v1/projects/{id}/search` | Test retrieval `{query, k}`, returns chunks with scores |
| DELETE | `/api/v1/projects/{id}/index` | Remove all indexed data for the project |

## Workflow and agents (`workflow`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/workflow/stages` | The fixed list of stages and what each one produces |
| POST | `/api/v1/projects/{id}/workflow` | Start a workflow run |
| GET | `/api/v1/projects/{id}/workflow` | The current run and the status of every stage |
| POST | `/api/v1/stages/{stage_id}/agent-runs` | Run an agent `{agent: planner \| reviewer, model_id, instructions}` |
| GET | `/api/v1/agent-runs/{id}` | Agent run status and output |
| PATCH | `/api/v1/stages/{stage_id}` | Edit the draft output by hand |
| POST | `/api/v1/stages/{stage_id}/approve` | Approve the stage (`{note}`), move to the next one |
| POST | `/api/v1/stages/{stage_id}/request-changes` | Send it back `{note}` |
| POST | `/api/v1/stages/{stage_id}/skip` | Skip the stage `{note}` |

## Teaching (`teaching`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/projects/{id}/teaching-notes` | List notes |
| POST | `/api/v1/projects/{id}/teaching-notes` | Generate a note on request `{concept?, message_id?, stage_key?, model_id}` |
| GET | `/api/v1/teaching-notes/{id}` | Get one note |
| DELETE | `/api/v1/teaching-notes/{id}` | Delete a note |
| GET | `/api/v1/projects/{id}/concepts` | The passive "concepts for this project" list |
| POST | `/api/v1/projects/{id}/concepts/refresh` | Rebuild the concept list (also runs silently after a stage is approved) |
| POST | `/api/v1/concepts/{id}/dismiss` | Hide a concept from the list |

## Execution (`execution`), Later, not built in v0.1

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/projects/{id}/executions` | Request a command run in the sandbox |
| POST | `/api/v1/executions/{id}/approve` | Approve the request (the human approval step) |
| POST | `/api/v1/executions/{id}/reject` | Reject the request |
| GET | `/api/v1/executions/{id}` | Status, exit code and output |
