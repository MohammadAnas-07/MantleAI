# Data model

Everything lives in one PostgreSQL database. Each table is owned by exactly one module (see
`docs/architecture.md`). There is no SQL here; the tables are created in `feat/database-models`.

Conventions: every table has `id` (UUID), `created_at` and `updated_at` (UTC). "FK" means
foreign key. Enums are stored as short strings.

## Structured vs vector

| Kind | What | Where |
| --- | --- | --- |
| **Vector** | Embeddings of project file chunks | `chunks.embedding` (pgvector, HNSW index, cosine) |
| **Structured** | Everything else: projects, memory, messages, keys, usage, workflow, notes, audit | Normal tables, normal queries |

Memory items, tasks and decisions are **not** embedded in v0.1. They are fetched with normal
queries (for example "open tasks" or "accepted decisions"), as `vision.md` asks.

## projects module

**Project**
- `name`, `description`
- `root_path`: the local folder to index (nullable)
- `default_model_id` → ModelConfig (nullable)
- `archived_at` (nullable)

**MemoryItem**: requirements, decisions and tasks in one table.
- `project_id` → Project
- `kind`: `requirement` | `decision` | `task`
- `title`, `body` (markdown)
- `status`: `proposed` | `active` | `done` | `rejected` | `superseded`
- `priority`: `low` | `medium` | `high` (nullable)
- `source`: `user` | `chat` | `agent`
- `source_message_id` → Message (nullable), `source_agent_run_id` → AgentRun (nullable)
- `stage_key` (nullable): the workflow stage it came from

## conversations module

**Conversation**
- `project_id` → Project
- `title`
- `current_model_id` → ModelConfig

**Message**
- `conversation_id` → Conversation
- `role`: `user` | `assistant` | `system`
- `content` (text)
- `model_id` → ModelConfig (nullable for user messages)
- `status`: `complete` | `streaming` | `error` | `cancelled`
- `error_code` (nullable), `token_count`

**ContextHandoff**: one row per model switch.
- `conversation_id` → Conversation
- `from_model_id`, `to_model_id` → ModelConfig
- `reason`: `user_choice` | `rate_limit` | `context_limit` | `provider_error`
- `summary` (text, nullable: empty if the full history fit)
- `summary_up_to_message_id` → Message (nullable)
- `tokens_before`, `tokens_after`

**MessageContext**: what was used to answer one message.
- `message_id` → Message
- `source_type`: `chunk` | `memory_item` | `handoff`
- `source_id` (UUID of the Chunk, MemoryItem or ContextHandoff)
- `score` (nullable), `rank`

## llm module (LLM gateway)

**ProviderCredential**
- `provider`: `openai` | `anthropic` | `google` | …
- `label`
- `encrypted_key` (bytes, Fernet), `key_hint` (last 4 characters)
- `last_tested_at`, `last_test_ok`

**ModelConfig**
- `provider`, `litellm_model` (for example `anthropic/claude-...`), `display_name`
- `kind`: `chat` | `embedding`
- `context_window`, `max_output_tokens`, `embedding_dimensions` (embedding models only)
- `input_cost_per_mtok`, `output_cost_per_mtok` (nullable)
- `enabled`

**UsageRecord**
- `model_id` → ModelConfig
- `purpose`: `chat` | `handoff_summary` | `embedding` | `agent` | `teaching`
- `project_id`, `conversation_id`, `message_id`, `agent_run_id` (all nullable)
- `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`
- `status`, `error_code`

## rag module

**IndexRun**
- `project_id` → Project
- `status`: `running` | `done` | `failed` | `cancelled`
- `files_seen`, `files_indexed`, `files_skipped`, `chunks_created`
- `error` (nullable), `finished_at`
- `embedding_model_id` → ModelConfig

**Document**: one indexed file.
- `project_id` → Project
- `path` (relative to `root_path`), `content_hash`, `size_bytes`, `language`
- `last_index_run_id` → IndexRun

**Chunk**
- `document_id` → Document, `project_id` → Project (copied here for fast filtering)
- `ordinal`, `text`, `start_line`, `end_line`, `token_count`
- `embedding` (vector; the dimension is fixed by the chosen embedding model)

## workflow module

**WorkflowRun**
- `project_id` → Project
- `status`: `active` | `completed` | `abandoned`
- `current_stage_key`

**StageState**: one row per stage per run. The stage list itself is fixed in code.
- `workflow_run_id` → WorkflowRun
- `stage_key` (for example `requirements`), `position`
- `status`: `not_started` | `drafting` | `awaiting_approval` | `approved` | `changes_requested` | `skipped`
- `output` (markdown, the current draft)
- `decision_note` (the user's comment), `decided_at`

**AgentRun**
- `stage_state_id` → StageState
- `agent`: `planner` | `reviewer`
- `model_id` → ModelConfig
- `input_summary`, `output` (markdown)
- `status`: `running` | `done` | `failed`
- `finished_at`

## teaching module

**TeachingNote**
- `project_id` → Project
- `concept` (for example "database indexing")
- `what`, `why_here`, `how` (markdown sections)
- `source_message_id` → Message (nullable), `stage_key` (nullable)
- `model_id` → ModelConfig

## execution module (Later, not created in v0.1)

**ExecutionRun**
- `project_id` → Project, `requested_by_agent_run_id` → AgentRun (nullable)
- `command`, `sandbox_image`
- `status`: `pending_approval` | `approved` | `running` | `done` | `failed` | `rejected`
- `exit_code`, `stdout`, `stderr` (truncated), `started_at`, `finished_at`

## Shared

**AuditEvent**: security-relevant actions only.
- `event_type` (for example `credential.added`, `index.started`, `stage.approved`)
- `entity_type`, `entity_id`
- `details` (JSON, never secrets or file contents)

## Relationships

```
Project 1─* Conversation 1─* Message 1─* MessageContext
        │               └─* ContextHandoff
        ├─* MemoryItem
        ├─* IndexRun
        ├─* Document 1─* Chunk
        ├─* WorkflowRun 1─* StageState 1─* AgentRun
        ├─* TeachingNote
        └─* ExecutionRun            (later)
ModelConfig 1─* Message / UsageRecord / AgentRun / ContextHandoff
ProviderCredential: one or more per provider, used by ModelConfig rows of that provider
```

Deleting a project deletes all its rows (cascade). Credentials, models and audit events are global.
