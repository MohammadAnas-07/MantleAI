# Roadmap

Work happens in this order, one branch per item. Branch names follow the Git conventions in
`CLAUDE.md`. Items are grouped by phase; goals, demos, dates and exit criteria are in
[`docs/phases.md`](phases.md). Phases 1–5 make up v0.1 (see `docs/mvp-scope.md`).

## [Phase 1: Switch models without losing context](phases.md#phase-1-switch-models-without-losing-context)

| Status | Branch | Goal |
| --- | --- | --- |
| Done | `chore/project-scaffold` | Project setup: FastAPI skeleton, `/health`, Docker PostgreSQL, tooling. |
| Done | `docs/project-documentation` | Architecture, requirements, scope, data model, API outline, security, ADRs. |
| Done | `fix/bind-database-to-localhost` | Publish PostgreSQL on 127.0.0.1 only. |
| Done | `docs/product-and-process-docs` | Idea, PRD, rules, phases and working memory. |
| Done | `chore/pin-dependencies` | Version ranges in `pyproject.toml` and a `requirements.lock` file, so every install is reproducible. |
| Done | `feat/database-models` | Alembic setup and the v0.1 tables from `docs/data-model.md`, with migration tests. |
| Done | `feat/llm-gateway` | Key test (the encryption helper and table exist from `feat/database-models`), model catalog, streaming chat and embeddings through LiteLLM, usage records, fake provider for tests. |
| Done | `feat/model-switching` | Conversations and streaming messages, context builder, rolling summary, handoff preview and switch. |

## [Phase 2: Project memory survives a switch](phases.md#phase-2-project-memory-survives-a-switch)

| Status | Branch | Goal |
| --- | --- | --- |
| Done | `feat/project-memory` | CRUD for requirements, decisions and tasks, fed into the context builder as pinned items. |

## [Phase 3: Answers that cite your code](phases.md#phase-3-answers-that-cite-your-code)

| Status | Branch | Goal |
| --- | --- | --- |
| Done | `feat/project-indexing-rag` | Index a local folder into pgvector, re-index only changed files, retrieve and cite top-k chunks in chat. |

## [Phase 4: Workflow, agents and teaching](phases.md#phase-4-workflow-agents-and-teaching)

| Status | Branch | Goal |
| --- | --- | --- |
| Done | `feat/workflow-and-agents` | Fixed workflow stages, Planner and Reviewer agents, approve, skip or reopen a stage; approve or reject a Planner draft; approval of AI-proposed memory items. |
| Done | `feat/project-profile` | Build the project profile (languages, dependencies from `pyproject.toml`, `requirements.txt`, `package.json`, markers such as Dockerfile, migrations, CI) at the end of each index run, without an LLM, and serve `GET /projects/{id}/profile`. The concepts list in `feat/teaching-layer` reads it. Also: the profile goes into every model's context, and a Profile tab shows it. |
| | `feat/profile-summary` | A model-written profile summary (purpose, architecture, conventions, constraints) on request only: estimate and confirm first, purpose `project_profile`, a draft until approved, edited or rejected, immutable versions with a current pointer and history (`project_profile_versions` in `projects`; the run in `agent_runs`). Added 2026-11-21 when the facts were split from the summary. |
| | `feat/teaching-layer` | Project-aware "what, why, how" teaching notes on request, and the rule-based concepts list. |

## [Phase 5: Workspace UI (v0.1 complete)](phases.md#phase-5-workspace-ui-v01-complete)

| Status | Branch | Goal |
| --- | --- | --- |
| Done | `feat/frontend-workspace` | React + Vite + TS + Tailwind UI for everything above (design in `docs/design-app.md`). The teaching screen waits for its backend. |
| Done | `feat/workflow-ui` | The workflow page: stages, the gap finder, and Planner and Reviewer runs with approval. |
| Review | `feat/app-redesign` | One visual system for the whole app (`docs/design-app.md`): tokens, a shared UI kit, clearer shell and states. No new feature, no API change. |

## [Phase 6: Safe execution, accounts and open-source release](phases.md#phase-6-safe-execution-accounts-and-open-source-release)

| Status | Branch | Goal |
| --- | --- | --- |
| | `feat/sandboxed-tool-execution` | Run approved commands in a locked-down Docker sandbox. |
| | `feat/authentication` | User accounts and sessions, so Mantle can run beyond one local user. |
| | `chore/ci-and-deployment` | GitHub Actions for lint and tests, a production build and deployment setup. |
| Review | `feat/landing-page` | Static landing page in `landing/` with the editorial design in `docs/design-landing.md` (replaces the grunge direction). Built and checked in CI, not hosted yet. |
