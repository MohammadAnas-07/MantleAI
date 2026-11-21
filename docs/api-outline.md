# API outline

REST + JSON, under `/api/v1`, except `/health`. Every operation has a tag and an `operationId` equal to the route function's name (for example `list_projects`), so generated clients get stable names; `backend/scripts/export_openapi.py` writes the schema without a server. Streaming uses server-sent events (SSE). There is
no auth in v0.1: every request runs as the default local user, and every query filters by that
user's `user_id` (see `docs/security.md`). Every write request must send
`Content-Type: application/json`.

Browsers may call the API only from `CORS_ALLOWED_ORIGINS` (the Vite dev server), and only with
a Host header in `ALLOWED_HOSTS` (localhost or 127.0.0.1); any other host gets 400
`invalid_host`. The frontend's types come from this API's OpenAPI schema
(`frontend/src/lib/api/schema.ts`, `npm run gen:api`).

Errors look the same everywhere: `{"error": {"code": "rate_limited", "message": "...", "details": {}}}`.

## System

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | API status, database `up`/`down`, and `keys`: `none`, `ok`, `unreadable` (the current `MASTER_ENCRYPTION_KEY` can't decrypt the newest saved key of some provider) or `unknown` (database down). A status word only, never a key or ciphertext; answers within about 2 s and never fails |
| GET | `/api/v1/me` | The current user (in v0.1, always the default local user) |
| GET | `/api/v1/audit-events` | List recent audit events (filter by type). **Not built yet**: events are written (a key added or deleted) but there is no route to read them |

## LLM gateway (`llm`)

Built in `feat/llm-gateway`. Write requests without `Content-Type: application/json` get 415.
No response ever contains an API key; credentials show `key_hint` (last 4 characters). Models
come from a default catalog added by `python -m app.db.seed`; an embedding model is enabled only
if its dimension matches `EMBEDDING_DIMENSIONS`. Gateway errors use the codes `rate_limited`
(429, a short limit: retrying can help), `quota_exhausted` (429, the quota is used up, for example
a per-day quota, or the provider asked for a wait over `LLM_QUOTA_EXHAUSTED_MIN_WAIT_SECONDS`;
never retried), `context_too_long` (413), `auth_failed` (401), `provider_unavailable` (503,
also when the provider is silent for `LLM_TIMEOUT_SECONDS`), `no_credential`,
`credential_unreadable` (a key is saved but the current master key can't decrypt it; the message
says to restore the previous master key or enter the key again; the saved key is left as it is)
and `model_unavailable` (422). Any error no handler knows is a 500 `internal_error` in the same
error shape, with CORS headers, and only its type is logged.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/providers` | List supported providers, whether a key is set, and whether the provider can do embeddings |
| GET | `/api/v1/credentials` | List saved keys (label, provider, last 4 characters only, and `readable`: false when the current master key can't decrypt it) |
| POST | `/api/v1/credentials` | Save a key `{provider, label, api_key}` (encrypted, never returned) |
| POST | `/api/v1/credentials/{id}/test` | Body `{}`. Make a tiny test call with this key (1 output token, logged as `key_test`); returns `{ok, error_code, model_id, tested_at}` |
| DELETE | `/api/v1/credentials/{id}` | Delete a key |
| GET | `/api/v1/models` | List models (`kind`, context window, enabled) |
| PATCH | `/api/v1/models/{id}` | Enable or disable a model, override its context window |
| GET | `/api/v1/settings/models` | The utility model (null = the active model), the embedding model, and `background_summary_enabled` |
| PATCH | `/api/v1/settings/models` | Change any of the three (changing the embedding model means re-indexing; turning background summaries off stops all background LLM calls) |
| GET | `/api/v1/usage` | Token and cost totals (filter by project, model, date), grouped by `purpose` and `trigger`, so each background purpose is its own line |
| GET | `/api/v1/usage/records` | Single calls, newest first (`since`, `limit` 1-500, default 100): model, purpose, trigger, status, error code, tokens, cost, latency, project and conversation ids. Metadata only, never prompts or replies. Used by the frontend's activity log |

## Projects and memory (`projects`)

Built: list, create, get, update and delete projects, and project memory
(`feat/project-memory`). Not built yet: description changes, archive, and approve/reject (they need
AI-proposed items, Phase 4). Every memory query filters by user and project; another user's or
another project's item is a 404. Text fields are trimmed and validated (422 names the field).
Edits are last-write-wins.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/projects` | List projects, each with `root_path`, `indexed`, `last_indexed_at`, `needs_reindex` and `reindex_reasons` (a fixed number of queries, whatever the project count). Served by `app/api/projects.py`, which combines projects and rag |
| POST | `/api/v1/projects` | Create a project `{name, description?, root_path?}`; `root_path` is checked like `PUT /source` (422 `invalid_source_path`) |
| GET | `/api/v1/projects/{id}` | Get one project, with the same index fields |
| PATCH | `/api/v1/projects/{id}` | `{name?, default_model_id?}` (at least one; `null` clears the default model). An unknown, disabled or non-chat model is 422 `model_unavailable`; a model without a saved key is allowed. The folder changes through `PUT /projects/{id}/source`; description and archive are not built |
| DELETE | `/api/v1/projects/{id}` | Delete a project and all its data (memory, conversations, index, runs cascade; usage rows stay). 409 `index_in_progress` while an index run is queued or running |
| GET | `/api/v1/projects/{id}/memory` | List memory items: filter by `kind`, `status`; `limit` (1-100, default 50) and `offset`; ordered by `created_at`, then id. Returns `{items, total, limit, offset}` |
| POST | `/api/v1/projects/{id}/memory` | Add an item `{kind, title, body?, status?, priority?, why?, alternatives?, decided_at?}`. 409 `memory_limit_reached` past 500 per kind |
| GET | `/api/v1/memory/{item_id}` | One item, with `depends_on_ids` and `is_blocked` (tasks) and `supersedes_ids` / `superseded_by_id` (decisions). Every item view also has `source` (`user` or `agent`) and, for items saved from an agent run, `source_agent_run_id` and `stage_key` |
| PATCH | `/api/v1/memory/{item_id}` | Change only the fields sent (`null` clears an optional text field); an empty body is a 422. `superseded` can't be set here; a superseded decision's status is locked (409) |
| POST | `/api/v1/memory/{item_id}/supersede` | Replace a decision: `{"decision": {...}}` creates the new one, `{"by_id": ...}` uses an existing one. Returns `{superseded, by}`. 409 if already superseded or if it would loop |
| POST | `/api/v1/memory/{item_id}/dependencies` | The task depends on `{depends_on_id}` (same project, no cycles: 409 `dependency_cycle`). Adding an existing link changes nothing |
| DELETE | `/api/v1/memory/{item_id}/dependencies/{depends_on_id}` | Remove a dependency |
| GET | `/api/v1/projects/{id}/memory/pinned?model_id=` | What would be pinned for that model now: the exact text, its tokens, the share limit, and the ids left out with the reason (`kind_cap` or `budget`). No LLM call |
| POST | `/api/v1/memory/{item_id}/approve` | Approve a `proposed` item. **Not built yet** (Phase 4) |
| POST | `/api/v1/memory/{item_id}/reject` | Reject a `proposed` item. **Not built yet** (Phase 4) |
| DELETE | `/api/v1/memory/{item_id}` | Delete an item; its dependency links go too, and a decision it superseded becomes `accepted` again |

## Conversations and model switching (`conversations`)

Built in `feat/model-switching`. The conversation in Mantle's database is the source of truth;
messages are stored provider-neutral with a `sequence` number. Mantle never switches models by
itself: `context_too_long` (413), `rate_limited` and `quota_exhausted` errors carry `details.suggested_models`
(enabled chat models the user has a key for: bigger context window, or another provider).
A second reply or a switch while a reply is streaming gets 409 `generation_in_progress`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/projects/{id}/conversations` | List the project's conversations |
| POST | `/api/v1/projects/{id}/conversations` | Create one `{title, model_id}` |
| GET | `/api/v1/conversations/{id}` | Get a conversation and its current model |
| PATCH | `/api/v1/conversations/{id}` | `{title?, code_context_enabled?}` (at least one). `code_context_enabled: false` turns project code retrieval off for this conversation (default on) |
| DELETE | `/api/v1/conversations/{id}` | Delete |
| GET | `/api/v1/conversations/{id}/messages` | List messages by `sequence` (paged with `after_sequence`, `limit`) |
| POST | `/api/v1/conversations/{id}/messages` | Send `{content}`. The response is an SSE stream: `message_start` (with `sources`: the retrieved code blocks, path, lines, scores, no text), zero or more `warning` (`{code, message, details}`: `retrieval_failed` when the query embedding failed, `needs_reindex`; the reply still comes), `delta` (text), then `message_end` (with usage) or `error` (with `suggested_models` for rate limits and context limits). In an indexed project the message is first embedded as a search query (purpose `embedding`, trigger `user`) unless the conversation turned code context off. The reply is saved when the stream ends; if the client disconnects, the upstream call is cancelled and the partial text is saved with status `cancelled`. Purpose `chat`, trigger `user`. The first message sets the title (first 60 characters; no LLM call) |
| POST | `/api/v1/messages/{id}/cancel` | Stop a reply that is still streaming. **Not built yet**; closing the stream cancels the reply |
| GET | `/api/v1/messages/{id}/context` | Sources and memory items used for this reply. **Not built yet**; the code used is already stored as `message_contexts` rows (chunk ids and line ranges) and sent in `message_start` |
| GET | `/api/v1/conversations/{id}/summary` | The current rolling summary, the message `sequence` range it covers, whether a job is running, and the last job error |
| GET | `/api/v1/conversations/{id}/handoff-preview?model_id=` | Exactly what would be sent to that model: each section (system, pinned items, summary, recent messages, retrieved context) with its content and tokens, the budget (context window - reserved output - safety margin), the total, what is dropped, `pinned` (its tokens, limit, and the item ids left out with the reason), `retrieved` (its tokens, its limit of 30% of the budget, the blocks `used` and `dropped` with path, lines, score and reason `share` or `context_budget`; the code is the one sent with the newest reply, read back from its message contexts), `has_key`, and `will_build_summary` with its input tokens. No LLM call (not even a query embedding); never contains keys |
| POST | `/api/v1/conversations/{id}/switch-model` | Switch `{model_id, reason}`. Checks the model exists and the user has a key for its provider. Never calls the old model. If background summaries are off, the NEW model writes the summary now (purpose `switch_summary`, trigger `user`). Creates a ContextHandoff whose `note` (built without an LLM, never sent to a model) lists messages carried verbatim, the summary range and size, pinned items and what was dropped. Returns `{conversation, handoff, preview}` |
| GET | `/api/v1/conversations/{id}/handoffs` | History of model switches |

## RAG (`rag`)

Built in `feat/project-indexing-rag`. The only model calls are embeddings, through the gateway
with purpose `embedding` and trigger `user` (they show in `GET /usage`). Another user's or
another project's data is a 404. Index runs are in-process background tasks: at most one queued
or running run per project (409 `index_in_progress`); a server restart marks a leftover run
`failed` with error `interrupted`. Run statuses: `queued`, `running`, `succeeded`, `failed`,
`cancelled`.

| Method | Path | Purpose |
| --- | --- | --- |
| PUT | `/api/v1/projects/{id}/source` | Set or change the folder to index `{root_path}`. Must be absolute, exist, be a readable folder; a filesystem root, the home folder or a folder above it is refused (422 `invalid_source_path`, `details.reason`). Stored as the real path. Indexed data stays; a new folder makes the project `needs_reindex` (`source_changed`) until it is indexed again. Returns the index status |
| GET | `/api/v1/projects/{id}/index` | Index status: `indexed`, `last_indexed_at`, `needs_reindex`, `reindex_reasons` (`embedding_model_changed`, `source_changed`), `embedding_models`, `files`, `active_run_id` |
| POST | `/api/v1/projects/{id}/index/estimate` | Body `{}`. What indexing would do now: files to index, unchanged, skipped and deleted; segments to embed and reused; tokens (about 4 characters each); cost; provider and model; the limit; the skip report. Reads the folder; no model call |
| POST | `/api/v1/projects/{id}/index` | Start (re-)indexing `{force?}`. Returns 202 `{run_id, status, estimate}`. 422 `no_source_path`, `model_unavailable` or `no_credential`; 409 `index_in_progress`; 409 `cost_limit_exceeded` (with `details.estimate`) when the estimate is above `INDEX_COST_LIMIT_USD` and `force` is not true |
| GET | `/api/v1/projects/{id}/index-runs` | List index runs, newest first (`limit`) |
| GET | `/api/v1/index-runs/{run_id}` | One run: status, error, counters (`files_seen`, `files_indexed`, `files_skipped`, `files_unchanged`, `chunks_created`, `tokens`, `cost_estimate_usd`), estimate, skip report (count and example paths per reason) |
| POST | `/api/v1/index-runs/{run_id}/cancel` | Body `{}`. A queued run is cancelled at once; a running one stops before its next batch (finished batches stay) |
| GET | `/api/v1/projects/{id}/documents` | Files of the index by path: `status` (`pending`, `indexed`, `skipped`), `skip_reason`, language, size, lines, `parse_fallback`. Filter `status`; `limit`, `offset`; `counts` per status. Folders and `.gitignore` matches are only counted in the run's skip report |
| DELETE | `/api/v1/projects/{id}/index` | Remove all file rows and chunks of the project (runs stay as history). 409 while a run is active |
| POST | `/api/v1/projects/{id}/search` | **Dev only** (404 unless `APP_ENV=development`). `{query, top_k?, mode?: hybrid \| vector \| text, path_prefix?, language?}`. Embeds the query and returns merged results with path, lines, language, symbol, `vector_rank`, `text_rank`, fused `score` and text, plus `needs_reindex`. 422 `invalid_query` when the query is empty or over `RETRIEVAL_QUERY_MAX_CHARS`, or `top_k` is over `RETRIEVAL_MAX_TOP_K`; 409 `not_indexed`; no match is an empty list |
| GET | `/api/v1/projects/{id}/profile` | The project profile (languages, dependencies, markers), built without an LLM. **Not built yet** (`feat/project-profile`) |

## Workflow and agents (`workflow`)

Built in `feat/workflow-and-agents` (replaces the earlier `/stages/{stage_id}/...` sketch). Stages
come from `app/modules/workflow/stages.yaml`, checked at startup. A project without a stored
workflow (made before this feature) reads as the first stage; GET writes nothing, and the first
change stores it with a `created` event. Every transition is saved as an append-only event and
uses a version check; approve and skip also take the `stage_id` the user means. Of two requests
at the same moment one wins, the other gets 409 `workflow_changed`. `stage_id` stays optional
for scripts and `/docs`; the UI always sends it, because without it a request that arrives just
after another approval approves the next stage. Reasons are trimmed, required and at most `WORKFLOW_REASON_MAX_LENGTH` (500).
If the stored stage no longer exists in the YAML, every call except reset answers 409
`unknown_stage` with `details.reset_path`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/workflow/stages` | The stage definitions in order: id, title, goal, checklist, artifact rules |
| GET | `/api/v1/projects/{id}/workflow` | Status (`active` \| `completed`), current stage, version, every stage with its checklist (`done`), artifact rules (`have`, `need`, `met`), `unmet` and `ready`, the newest 100 `events` (oldest first) and `events_total` (all events). A change answers the same shape, built from the memory it read before the change |
| POST | `/api/v1/projects/{id}/workflow/checklist` | Tick or untick `{stage_id, item_id, done}`. 422 for an unknown stage or item |
| POST | `/api/v1/projects/{id}/workflow/approve` | Approve the current stage and move to the next `{stage_id?, force?, reason?}`. 409 `stage_gate_unmet` with `details.unmet` (required checklist items, artifact rules with `have`/`need`) unless `force=true` with a reason. The last stage completes the workflow; then 409 `workflow_completed` |
| POST | `/api/v1/projects/{id}/workflow/skip` | Skip the current stage `{reason, stage_id?}` (no gate) |
| POST | `/api/v1/projects/{id}/workflow/reopen` | Go back to an earlier stage `{stage_id, reason}`; it and later stages become pending, ticks stay. 409 `not_an_earlier_stage` |
| POST | `/api/v1/projects/{id}/workflow/reset` | Back to the first stage `{reason}`; statuses cleared, ticks of existing stages kept |
| POST | `/api/v1/projects/{id}/gap-finder` | Run the gap finder now `{model_id, force?}` (one call, at most one retry, purpose `agent_run`). Returns the saved run with `result` (`missing_steps`, `risks`, `technical_debt`, `scalability_concerns`) and `warnings`. A failed run is saved and its error returned (502 `invalid_output` or `step_timeout`, or the gateway error) with `details.run_id`. Its `running` row is committed before the model call, so another start sees it at once (409 `agent_run_in_progress`); if the request dies or crashes, the run ends `failed` with `error` `interrupted` or `internal_error` |
| GET | `/api/v1/projects/{id}/gap-finder` | Past gap finder runs, newest first |
| POST | `/api/v1/projects/{id}/agent-runs` | 202: start `{run_type: plan \| review, model_id, requirement_id? \| requirement_text?, use_code_context?, force?}` in the background. A plan run needs exactly one requirement; a review run none. The response has the `estimate` |
| POST | `/api/v1/projects/{id}/agent-runs/estimate` | The same body as a start. Returns what a start would get: `steps`, `input_tokens`, `output_tokens`, `cost_usd` (null for a model without catalog prices), `cost_limit_usd`, `model`, `over_limit`. Makes the start's checks (404, 413, 422) but creates no run and calls no model; `force` is ignored. The UI shows it before the user confirms a start |
| GET | `/api/v1/projects/{id}/agent-runs` | Plan and review runs, newest first (at most 50), as summaries: `id`, `project_id`, `run_type`, `status`, `stage_id`, `model_id`, `error`, `input_tokens`, `output_tokens`, `cost_usd`, `cancel_requested_at`, `created_at`, `started_at`, `finished_at`, `decided_at`. No `result`, `input`, `estimate`, `warnings` or `steps`: they come with `GET /agent-runs/{id}` |
| GET | `/api/v1/agent-runs/{id}` | Status, estimate, result (`plan`, `review`), warnings, error, tokens, cost and `steps` |
| POST | `/api/v1/agent-runs/{id}/cancel` | Queued: cancelled now; running: stops at the next check (before every model call and every save) and always ends `cancelled`. Status changes are conditional updates, so a cancel is never overwritten. A run still `running` more than `AGENT_RUN_STALE_SECONDS` (900) after it started has lost its job (it died while the server stayed up): the cancel ends it `cancelled` at once. 409 `agent_run_not_active` when the run is finished or waiting for approval; 409 `agent_run_not_cancellable` for a gap finder run |
| POST | `/api/v1/agent-runs/{id}/approve` | `{all: true}` or `{tasks: [{index, title?, description?, priority?}], decisions: [{index, title?, what?, why?, alternatives?}]}`. Saves the chosen items in one transaction: tasks `todo`, decisions `proposed`, `source = agent`, `source_agent_run_id`, `stage_key`; dependencies between chosen tasks become links. Returns the new ids and warnings (`dependency_not_saved`). The run row is locked first: of two decisions at once, the second gets 409 `agent_run_not_waiting` and saves nothing. Chosen drafts are checked again against today's limits: 422 `draft_limits_changed`. 422 `invalid_draft` / `invalid_selection` |
| POST | `/api/v1/agent-runs/{id}/reject` | `{reason}`. Saves nothing. Locks the run like approve |

Agent and gap finder starts check, before any model call: the project (404), the model and its
key (422 `model_unavailable`, `no_credential`), the prompt size (413 `context_too_long` with
`details.suggested_models`), one queued or running run per project (409
`agent_run_in_progress`) and the estimate against `AGENT_RUN_COST_LIMIT_USD` (0.50; 409
`cost_limit_exceeded` with `details.estimate`, unless `force=true`). A model with no price in the catalog
has no estimate, so it is refused with 422 `model_not_priced` (even with `force`) unless
`AGENT_ALLOW_UNPRICED_MODELS=true`. Run statuses: `queued`,
`running`, `waiting_for_approval`, `approved`, `rejected`, `completed` (review and gap finder),
`failed`, `cancelled`. At startup, queued and running runs become `failed` with `error` =
`interrupted`.

## Teaching (`teaching`)

**Not built yet** (Phase 4, `feat/teaching-layer`). The tables exist; none of these routes does.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/projects/{id}/teaching-notes` | List notes |
| POST | `/api/v1/projects/{id}/teaching-notes` | Generate a note on request `{concept?, message_id?, stage_key?, model_id}` |
| GET | `/api/v1/teaching-notes/{id}` | Get one note |
| DELETE | `/api/v1/teaching-notes/{id}` | Delete a note |
| GET | `/api/v1/projects/{id}/concepts` | The passive "concepts for this project" list |
| POST | `/api/v1/projects/{id}/concepts/refresh` | Rebuild the list with the rule-based selector. **No LLM call.** It also runs after an index run and after a stage is approved |
| POST | `/api/v1/concepts/{id}/dismiss` | Hide a concept from the list |

## Execution (`execution`), Later, not built in v0.1

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/projects/{id}/executions` | Request a command run in the sandbox |
| POST | `/api/v1/executions/{id}/approve` | Approve the request (the human approval step) |
| POST | `/api/v1/executions/{id}/reject` | Reject the request |
| GET | `/api/v1/executions/{id}` | Status, exit code and output |
