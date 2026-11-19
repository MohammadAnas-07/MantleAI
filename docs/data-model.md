# Data model

Everything lives in one PostgreSQL database. Each table is owned by exactly one module (see
`docs/architecture.md`). There is no SQL here; the tables are created in `feat/database-models`.

Conventions:

- Every table has `id` (UUID), `created_at` and `updated_at` (UTC).
- **Every user-data table has `user_id` → User** (not null, indexed). That is every table below
  except User and ModelConfig. Child tables (Message, Chunk, StageState, …) carry `user_id` too,
  so every query can filter by user directly.
- "FK" means foreign key. Enums are stored as short strings (`VARCHAR(32)`, no PostgreSQL enum
  types and no CHECK constraints), so adding a value needs no migration.
- Every foreign key column is indexed. Constraint and index names follow one convention, set on
  the SQLAlchemy metadata in `app/db/base.py` (`pk_<table>`, `fk_<table>_<column>`,
  `uq_<table>_<columns>`, `ix_<table>_<column>`).
- Each module's tables are in `app/modules/<module>/models.py` (shared ones in
  `app/core/models.py`), with one repository per table in `repository.py`. A user-data repository
  is bound to one `user_id` and filters every query by it.

## Deletes (ON DELETE)

| Rule | Where | Why |
| --- | --- | --- |
| CASCADE | every `user_id` → users | Deleting a user deletes all their data. |
| CASCADE | `project_id` on memory items, conversations, index runs, documents, chunks, project profile, workflow runs, teaching notes, concept suggestions | A project owns these rows. |
| CASCADE | conversation → messages, summaries, handoffs; message → message contexts and the summaries/handoffs that point at it; document → chunks; workflow run → stage states → agent runs | Child rows mean nothing without their parent. |
| SET NULL | `usage_records.project_id`, `conversation_id`, `message_id`, `agent_run_id` | Cost history must survive deletes. |
| SET NULL | optional links: `projects.default_model_id`, `memory_items.source_message_id` / `source_agent_run_id`, `teaching_notes.source_message_id`, `concept_suggestions.teaching_note_id`, `context_handoffs.conversation_summary_id`, `user_model_settings.*_model_id` | The row stays useful without the link. |
| NO ACTION | every required `→ ModelConfig`, `documents.last_index_run_id`, `project_profiles.index_run_id` | A model in use can't be deleted (disable it with `enabled`). Index runs are deleted only with their project. |

SET NULL foreign keys are `DEFERRABLE INITIALLY DEFERRED`. One project delete cascades through
several tables, and a row whose link is cleared may still point at another row the same cascade
is deleting. The deferred check runs at commit, when the cascade is complete.

## Structured vs vector

| Kind | What | Where |
| --- | --- | --- |
| **Vector** | Embeddings of project file chunks | `chunks.embedding` (pgvector, HNSW index, cosine) |
| **Structured** | Everything else: users, projects, memory, messages, summaries, keys, usage, workflow, notes, audit | Normal tables, normal queries |

Memory items, tasks and decisions are **not** embedded in v0.1. They are fetched with normal
queries (for example "open tasks" or "accepted decisions"), as `vision.md` asks.

## Shared (`app/core`)

**User**
- `display_name`
- `is_local_default` (bool)
- v0.1 has exactly one row, the default local user, with the fixed id
  `00000000-0000-0000-0000-000000000001`. It is created by the seed script
  (`python -m app.db.seed`, safe to run twice), not by a migration. Auth later adds login fields;
  it doesn't change other tables.

**AuditEvent**: security-relevant actions only.
- `user_id` → User
- `event_type` (for example `credential.added`, `index.started`, `stage.approved`)
- `entity_type`, `entity_id`
- `details` (JSON, never secrets or file contents)

## projects module

**Project**
- `user_id` → User
- `name`, `description`
- `root_path`: the local folder to index (nullable). Validated by the rag module (absolute,
  exists, readable folder, not a filesystem root or the home folder) and stored as the real path
- `default_model_id` → ModelConfig (nullable)
- `archived_at` (nullable)

**MemoryItem**: requirements, decisions and tasks in one table. Written by the user through the
API, or saved from an agent run's drafts when the user approves them (never by an LLM alone). Statuses and priorities are per kind, checked in
`app/modules/projects/memory_service.py`. Edits are last-write-wins (no version check).
- `user_id` → User, `project_id` → Project
- `kind`: `requirement` | `decision` | `task`
- `title` (one line, at most `MEMORY_TITLE_MAX_LENGTH` = 200), `body` (at most
  `MEMORY_TEXT_MAX_LENGTH` = 5000; for a decision: what was decided). Text is trimmed; any Unicode
  is fine; control characters and null bytes are rejected.
- `status`, per kind:
  - decision: `proposed` | `accepted` (default) | `rejected` | `deprecated` | `superseded`
    (`superseded` only through the supersede action)
  - requirement: `draft` (default) | `approved` | `dropped`
  - task: `todo` (default) | `in_progress` | `done` | `blocked`
- `priority` (nullable): requirement `must` | `should` | `could`; task `high` | `medium` | `low`;
  decisions have none
- Decision only: `why`, `alternatives` (text), `decided_at` (not in the future; set to now when a
  decision is created as accepted or rejected without one)
- `superseded_by_id` → MemoryItem (nullable): the decision that replaced this one. Deleting the
  newer decision makes the older one `accepted` again. A superseded decision can't replace
  another one, which rules out loops.
- At most `MEMORY_MAX_ITEMS_PER_KIND` (500) items per kind per project (409 after that).
- `source`: `user` | `chat` | `agent` (`agent` only for drafts the user approved from an agent run)
- `source_message_id` → Message (nullable), `source_agent_run_id` → AgentRun (nullable)
- `stage_key` (nullable): the workflow stage it came from

**MemoryDependency**: task `task_id` depends on task `depends_on_id`.
- `user_id` → User, `project_id` → Project, `task_id` → MemoryItem, `depends_on_id` → MemoryItem
  (both CASCADE: deleting a task removes its links)
- Unique `(task_id, depends_on_id)`; a duplicate link is ignored. CHECK `task_id <> depends_on_id`.
- Both tasks must be in the same project, and a link that would make a cycle (any length) is
  refused (409). A task is `is_blocked` (computed, not stored) while any dependency isn't `done`;
  marking a blocked task done is allowed.

**Pinned memory** (not a table): what the ContextBuilder sends as `<pinned_items>`, built by
`app/modules/projects/pinned.py`. Order: accepted decisions; approved `must` then `should`
requirements; open tasks (`in_progress`, `todo`, `blocked`, then by priority); inside a group
`created_at`, then id. At most `PINNED_MAX_DECISIONS` / `_REQUIREMENTS` / `_TASKS` (30 each) and
`PINNED_MAX_SHARE` (25%) of the context budget; items longer than `PINNED_ITEM_MAX_CHARS` (600)
end in `[truncated]`. One line per item: `- [kind shortid status priority] title: body | why: ...`.
Same data gives byte-identical text. Data delimiters and chat-template markers inside items are
defanged.

## conversations module

**Conversation**
- `user_id` → User, `project_id` → Project
- `title`: set from the first 60 characters of the first message when empty (no LLM call)
- `current_model_id` → ModelConfig: a switch changes only this
- `generating_since` (nullable): lock, one reply or switch at a time (409 otherwise)
- `summary_started_at` (nullable): lock, one rolling-summary job at a time
- `summary_error` (nullable): error code of the last failed summary job
- `code_context_enabled` (bool, default true; migration `0006`): when false, no project code is
  retrieved for this conversation, so no query embedding is made
- A lock older than `CONVERSATION_LOCK_TIMEOUT_SECONDS` (600) is stale and can be taken over.

**Message**
- `user_id` → User, `conversation_id` → Conversation
- `sequence`: 1, 2, 3, ... per conversation (unique with `conversation_id`); the conversation's
  order, independent of timestamps
- `role`: `user` | `assistant` | `system` | `tool`
- `content` (JSON): a provider-neutral list of parts, validated by
  `app/modules/conversations/schemas.py`:
  `{"type": "text", "text"}`, `{"type": "tool_call", "id", "name", "arguments"}`,
  `{"type": "tool_result", "tool_call_id", "content", "is_error"}`. v0.1 agents have no tools, so
  only text parts are written for now; the format is ready for tools later.
- `model_id` → ModelConfig: the model that produced it (nullable for user messages)
- `status`: `complete` | `streaming` | `error` | `cancelled` (`cancelled` = incomplete: the client disconnected and the partial text was kept)
- `error_code` (nullable)
- `token_count`: tokens of this message's own content (for fitting history into a window)
- `input_tokens`, `output_tokens` (nullable): provider-reported usage of the call that produced it

**ConversationSummary**: the rolling summary, built in the background, or at switch time when
background summaries are off. A new row is added each time it's updated; the current one is the
row with the highest `to_sequence`. It is incremental: previous summary + messages after its
`to_sequence`. The latest user message and the last `CONTEXT_KEEP_RECENT_TURNS` turns are never
summarized.
- `user_id` → User, `conversation_id` → Conversation
- `from_sequence`, `to_sequence`: the messages it covers
- `summary` (text): decisions and why, constraints and preferences, files, errors, open questions
  (prompt `app/modules/conversations/prompts/summary_v1.txt`)
- `up_to_message_id` → Message: the last message this summary covers
- `model_id` → ModelConfig: the model that wrote it
- `built_at`: `background` | `switch`
- `token_count`

**ContextHandoff**: one row per model switch.
- `user_id` → User, `conversation_id` → Conversation
- `from_model_id`, `to_model_id` → ModelConfig
- `reason`: `user_choice` | `rate_limit` | `context_limit` | `provider_error`
- `conversation_summary_id` → ConversationSummary (nullable: none for short conversations)
- `first_raw_message_id` → Message (nullable): the oldest message carried over as-is; null when
  none is carried
- `tokens_before`, `tokens_after`: estimated context size on the old and the new model
- `note` (JSON): the handoff note shown to the user, built without an LLM and never sent to a
  model: messages carried verbatim, summary range and tokens, pinned items, what was dropped

**MessageContext**: what was used to answer one message.
- `user_id` → User, `message_id` → Message
- `source_type`: `chunk` | `memory_item` | `summary`
- `source_id` (UUID of the Chunk, MemoryItem or ConversationSummary)
- `score` (nullable), `rank`
- `start_line`, `end_line` (nullable; migration `0006`): for chunks, the lines that were sent.
  Ids and line ranges only, never the text. Written for each reply that used retrieved code
  (one row per chunk; chunks merged into one block share its rank, score and lines).

## llm module (LLM gateway)

**ProviderCredential**
- `user_id` → User
- `provider`: `openai` | `anthropic` | `google` | `voyage` | …
- `label`
- `encrypted_key` (bytes, Fernet), `key_hint` (last 4 characters)
- `last_tested_at`, `last_test_ok`

**ModelConfig**: shared catalog, not user data (no `user_id`).
- `provider`, `litellm_model` (for example `openai/text-embedding-3-small`), `display_name`
- `kind`: `chat` | `embedding`
- `supports_tools` (bool): when false, tool-call history is sent to the model as plain text
- `context_window`, `max_output_tokens`, `embedding_dimensions` (embedding models only)
- `input_cost_per_mtok`, `output_cost_per_mtok` (nullable)
- `enabled`

**UserModelSettings**: one row per user.
- `user_id` → User (unique)
- `utility_model_id` → ModelConfig (nullable: **null means "use the conversation's active model"**)
- `embedding_model_id` → ModelConfig (nullable until the user picks one; the intended default is a
  small OpenAI or Voyage model)
- `background_summary_enabled` (bool, default true): when false, no rolling-summary calls run in
  the background, and the summary is built at switch time instead (D10)

**UsageRecord**
- `user_id` → User
- `model_id` → ModelConfig
- `purpose`: `chat` | `rolling_summary` | `switch_summary` | `embedding` | `agent_run` |
  `teaching` | `key_test` (the tiny call made by "test key"); `agent` is an old, unused value
- `trigger`: `user` (the user directly asked) | `background` (they didn't). The usage view shows
  each `background` purpose as its own line. **Every LLM call writes a row; no exceptions.**
- `project_id`, `conversation_id`, `message_id`, `agent_run_id` (all nullable)
- `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`
- `status`: `success` | `error` | `cancelled`, `error_code`
- `error_detail` (nullable, up to 255 characters, migration `0007`): sanitized structured fields of
  the provider's error, for example `http=429 status=RESOURCE_EXHAUSTED quota_id=... retry_after_s=33`.
  Never the provider's free text, prompts or keys.

## rag module

**IndexRun**: one indexing job (migration `0005`).
- `user_id` → User, `project_id` → Project
- `status`: `queued` | `running` | `succeeded` | `failed` | `cancelled` (`done` before `0005`).
  At most one `queued` or `running` run per project: partial unique index
  `uq_index_runs_project_id_active`. A run left `queued` or `running` when the server starts is
  set to `failed` with `error` = `interrupted`.
- `files_seen`, `files_indexed`, `files_skipped`, `files_unchanged`, `chunks_created`, `tokens`
  (estimated, about 4 characters each), `cost_estimate_usd`
- `error` (nullable: an error code such as `rate_limited`, `auth_failed`, `source_missing`,
  `interrupted`, `internal_error`, `daily_quota_exhausted` (the provider's quota is used up; not
  retried, run it again after the reset to resume) or `rate_limit_wait_exceeded` (retries of one
  batch would wait longer than `EMBED_RETRY_MAX_TOTAL_WAIT_SECONDS`)), `started_at`, `finished_at`, `cancel_requested_at`
- `force` (bool): started above the cost limit on purpose
- `embedding_model_id` → ModelConfig, plus snapshots `embedding_model` (name) and `root_path`
- `estimate` (JSON): the estimate checked before the run; `skip_report` (JSON): count and up to
  5 example paths per skip reason

**Document**: one file of the project.
- `user_id` → User, `project_id` → Project
- `path` (relative to `root_path`, POSIX form), unique per project
- `status`: `pending` (its segments are being embedded) | `indexed` | `skipped`
- `skip_reason` (nullable): `sensitive_name`, `possible secret`, `too_large`, `too_many_files`,
  `too_many_segments`, `lock_file`, `minified`, `binary`, `unsupported_type`,
  `unsupported_encoding`, `empty`, `long_lines`, `unreadable`, `changed_while_reading`. Ignored
  folders, `.gitignore` matches and symlinks have no row; they are only counted in the run's
  `skip_report`.
- `content_hash` (sha256 of the LF-normalized text; null until every segment of that content is
  stored), `size_bytes`, `mtime_ns`, `line_count`, `language`
- `parse_fallback` (nullable): `syntax_error` or `no_grammar` when code was split by lines
- `embedding_model`: the model its chunks were made with
- `last_index_run_id` → IndexRun

**Chunk**: one segment of a document ("chunk" in table and column names).
- `user_id` → User, `document_id` → Document, `project_id` → Project (copied here for fast filtering)
- `ordinal`, `text`, `start_line`, `end_line` (1-based, inclusive, on the LF text), `token_count`
- `language`, `chunk_type` (`function` | `class` | `method` | `module` | `section` | `lines`),
  `symbol` (function or class name, `Class.method`, or a Markdown heading path)
- `content_hash`: sha256 of the text sent to the embedder (`File: path`, `Symbol: ...`, then the
  text). The same hash and model reuse the stored vector, so unchanged segments of an edited file
  are not embedded again.
- `search_text`: path, symbol and text with identifiers split into words (`healthCheck` →
  `healthcheck health check`); `search_tsv` is generated from it
  (`to_tsvector('simple', search_text)`, GIN index `ix_chunks_search_tsv`)
- `embedding` (vector, HNSW cosine index)
- `embedding_model` (the LiteLLM model name), `embedding_dimensions`; index
  `ix_chunks_project_id_embedding_model`. No unique `(document_id, ordinal)` since `0005`: while a
  changed file is being indexed, its old and new segments exist side by side.

**ProjectProfile**: facts about the project, built **without an LLM** at the end of each index
run. One row per project. The table exists; filling it is `feat/project-profile`.
- `user_id` → User, `project_id` → Project (unique)
- `languages` (JSON, for example `{"python": 42, "typescript": 10}`, the file counts)
- `dependencies` (JSON, names read from `pyproject.toml`, `requirements.txt`, `package.json`)
- `markers` (JSON, for example `dockerfile`, `compose`, `migrations`, `ci_workflows`, `tests`)
- `index_run_id` → IndexRun (the run that built it)

**Changing the embedding model:** the `embedding` column has one fixed dimension, the setting
`EMBEDDING_DIMENSIONS` in `app/core/config.py` (default 1536; HNSW allows at most 2000).
Migration `0001` froze it at 1536. **Changing the setting needs a new migration** that alters the
column and rebuilds the HNSW index (`ix_chunks_embedding_hnsw`, cosine), and every project must
be re-indexed. `tests/test_migrations.py` fails if the database and the setting disagree. Vectors from different models can't be compared, so changing
the model means re-indexing the project. Retrieval only uses chunks whose `embedding_model`
matches the query's model. A model with a different dimension also needs a migration to change
the column. The user's embedding model is `user_model_settings.embedding_model_id`, else
`DEFAULT_EMBEDDING_MODEL` (`gemini/gemini-embedding-001`, asked for 1536 dimensions; its native
size is 3072). A project whose chunks were made with another model is `needs_reindex`
(`embedding_model_changed`); so is one whose `root_path` differs from its last successful run
(`source_changed`). Both are computed when read, not stored.

## workflow module

Migration `0008` replaced the unused `workflow_runs` and `stage_states` tables of `0001` and
reshaped `agent_runs` (its old rows could not be mapped to a project and were deleted).

**ProjectWorkflow** (`project_workflows`): one row per project, stored on the first change
(until then a project reads as the first stage; GET writes nothing).
- `user_id` → User, `project_id` → Project (unique, CASCADE)
- `status`: `active` | `completed`
- `current_stage_id` (null once completed; may name a stage removed from `stages.yaml`, which
  the API reports as 409 `unknown_stage`)
- `stage_statuses` (JSON: stage id → `approved` | `skipped`; any other stage is pending, or
  current)
- `checklist` (JSON: stage id → ticked item ids)
- `version` (int): every transition updates only the version it read, then adds 1

Stage definitions are not a table: `app/modules/workflow/stages.yaml` (id, title, goal,
checklist items with `required`, artifact rules `min_memory_items` with `kind`, optional
`statuses` and `min`), checked at startup.

**WorkflowEvent** (`workflow_events`): append-only. The ORM refuses updates and a trigger
(`workflow_events_no_update`) refuses `UPDATE` in the database; rows go only with their project.
- `user_id`, `project_id`, `workflow_id` → ProjectWorkflow
- `seq` (identity): the sort order (events of one transaction share `created_at`)
- `action`: `created` | `tick` | `untick` | `approve` | `skip` | `reopen` | `reset` | `completed`
- `stage_id`, `item_id`, `actor` (`user`), `reason`, `forced`, `details` (JSON, for example the
  unmet gate items a forced approval passed over)

**AgentRun** (`agent_runs`): one Planner + Reviewer run, one Reviewer-only run, or one gap
finder run.
- `user_id`, `project_id` → Project (CASCADE), `model_id` → ModelConfig
- `run_type`: `plan` | `review` | `gap_finder`
- `status`: `queued` | `running` | `waiting_for_approval` | `approved` | `rejected` |
  `completed` | `failed` | `cancelled`. At most one `queued` or `running` run per project:
  partial unique index `uq_agent_runs_project_id_active`
- `stage_id` (the stage when it started), `prompt_version` (for example
  `planner_v1,reviewer_v1`)
- `input` (JSON: `requirement_id` or `requirement_text`, `use_code_context`, `force`),
  `estimate` (JSON: steps, tokens, cost, limit)
- `result` (JSON: the validated `plan` and `review`, or the gap report; drafts, not memory),
  `warnings` (JSON list: dropped references, trimmed memory, code context problems)
- `error`, `error_message`, `error_details` (JSON, for example `suggested_models`)
- `input_tokens`, `output_tokens`, `cost_usd` (sums of the steps)
- `cancel_requested_at`, `started_at`, `finished_at`, `decided_at`, `decision_reason`
- `saved_item_ids` (JSON list): memory items created when the user approved it

**AgentRunStep** (`agent_run_steps`): one model call (with at most one retry).
- `user_id`, `run_id` → AgentRun (CASCADE), `model_id` → ModelConfig
- `position`, `agent`: `planner` | `reviewer` | `gap_finder`, `prompt_version`
- `status`: `succeeded` | `failed`, `attempts`, `input_tokens_estimate`
- `output` (JSON, validated), `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `error`

Approved drafts become MemoryItems with `source = agent`, `source_agent_run_id` and `stage_key`
(columns from `0001`): tasks `todo`, decisions `proposed`. Every model call of a run writes a
UsageRecord with `purpose = agent_run`, `trigger = user` and `agent_run_id`.

## teaching module

**TeachingNote**: only created when the user asks.
- `user_id` → User, `project_id` → Project
- `concept` (for example "database indexing")
- `what`, `why_here`, `how` (markdown sections)
- `source_message_id` → Message (nullable), `stage_key` (nullable)
- `model_id` → ModelConfig

**ConceptSuggestion**: the passive "concepts for this project" list. It's built by the
rule-based selector only, with **no LLM call**. An LLM is called only when the user asks for an
explanation, which creates a TeachingNote.
- `user_id` → User, `project_id` → Project
- `rule_id`, `concept`
- `reason`: the rule's own "why" text, plus the facts that matched (for example "dependency: sqlalchemy")
- `status`: `new` | `dismissed` | `noted`
- `teaching_note_id` → TeachingNote (nullable: set once the user asks for a note)

The rules are a YAML file in the `teaching` module (not a table). Each rule looks like this:

```yaml
- id: database-indexing
  concept: Database indexing
  relevant_when:
    any:
      - dependency: sqlalchemy
      - marker: migrations
  why: Your project stores data in a database. Indexes decide how fast its queries are.
```

The selector checks `relevant_when` against the ProjectProfile, the project's memory items and
its approved workflow stages.

## execution module (Later, not created in v0.1; no table exists yet)

**ExecutionRun**
- `user_id` → User, `project_id` → Project, `requested_by_agent_run_id` → AgentRun (nullable)
- `command`, `sandbox_image`
- `status`: `pending_approval` | `approved` | `running` | `done` | `failed` | `rejected`
- `exit_code`, `stdout`, `stderr` (truncated), `started_at`, `finished_at`

## Relationships

```
User 1─* (every user-data table, via user_id)
     1─1 UserModelSettings
     1─* ProviderCredential, AuditEvent, UsageRecord
     1─* Project 1─* Conversation 1─* Message 1─* MessageContext
                 │               ├─* ConversationSummary
                 │               └─* ContextHandoff
                 ├─* MemoryItem
                 ├─* IndexRun
                 ├─* Document 1─* Chunk
                 ├─1 ProjectProfile
                 ├─* WorkflowRun 1─* StageState 1─* AgentRun
                 ├─* TeachingNote
                 ├─* ConceptSuggestion
                 └─* ExecutionRun            (later)
ModelConfig 1─* Message / ConversationSummary / UsageRecord / AgentRun / ContextHandoff
```

Deleting a project deletes all its rows (cascade). Credentials, settings and audit events belong
to the user, not to a project.
