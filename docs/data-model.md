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
- `root_path`: the local folder to index (nullable)
- `default_model_id` → ModelConfig (nullable)
- `archived_at` (nullable)

**MemoryItem**: requirements, decisions and tasks in one table.
- `user_id` → User, `project_id` → Project
- `kind`: `requirement` | `decision` | `task`
- `title`, `body` (markdown)
- `status`: `proposed` | `active` | `done` | `rejected` | `superseded`
- `priority`: `low` | `medium` | `high` (nullable)
- `source`: `user` | `chat` | `agent`
- `source_message_id` → Message (nullable), `source_agent_run_id` → AgentRun (nullable)
- `stage_key` (nullable): the workflow stage it came from

## conversations module

**Conversation**
- `user_id` → User, `project_id` → Project
- `title`: set from the first 60 characters of the first message when empty (no LLM call)
- `current_model_id` → ModelConfig: a switch changes only this
- `generating_since` (nullable): lock, one reply or switch at a time (409 otherwise)
- `summary_started_at` (nullable): lock, one rolling-summary job at a time
- `summary_error` (nullable): error code of the last failed summary job
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
- `purpose`: `chat` | `rolling_summary` | `switch_summary` | `embedding` | `agent` | `teaching`
  | `key_test` (the tiny call made by "test key")
- `trigger`: `user` (the user directly asked) | `background` (they didn't). The usage view shows
  each `background` purpose as its own line. **Every LLM call writes a row; no exceptions.**
- `project_id`, `conversation_id`, `message_id`, `agent_run_id` (all nullable)
- `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`
- `status`: `success` | `error` | `cancelled`, `error_code`

## rag module

**IndexRun**
- `user_id` → User, `project_id` → Project
- `status`: `running` | `done` | `failed` | `cancelled`
- `files_seen`, `files_indexed`, `files_skipped`, `chunks_created`
- `error` (nullable), `finished_at`
- `embedding_model_id` → ModelConfig

**Document**: one indexed file.
- `user_id` → User, `project_id` → Project
- `path` (relative to `root_path`), `content_hash`, `size_bytes`, `language`
- `last_index_run_id` → IndexRun

**Chunk**
- `user_id` → User, `document_id` → Document, `project_id` → Project (copied here for fast filtering)
- `ordinal`, `text`, `start_line`, `end_line`, `token_count`
- `embedding` (vector)
- `embedding_model` (the LiteLLM model name), `embedding_dimensions`

**ProjectProfile**: facts about the project, built **without an LLM** at the end of each index
run. One row per project.
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
the column.

## workflow module

**WorkflowRun**
- `user_id` → User, `project_id` → Project
- `status`: `active` | `completed` | `abandoned`
- `current_stage_key`

**StageState**: one row per stage per run. The stage list is fixed in code: `requirements`,
`architecture`, `technical_decisions`, `task_breakdown`, `implementation_plan`.
- `user_id` → User, `workflow_run_id` → WorkflowRun
- `stage_key`, `position`
- `status`: `not_started` | `drafting` | `awaiting_approval` | `approved` | `changes_requested` | `skipped`
- `output` (markdown, the current draft)
- `decision_note` (the user's comment), `decided_at`

**AgentRun**
- `user_id` → User, `stage_state_id` → StageState
- `agent`: `planner` | `reviewer`
- `model_id` → ModelConfig
- `input_summary`, `output` (markdown)
- `status`: `running` | `done` | `failed`
- `finished_at`

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
