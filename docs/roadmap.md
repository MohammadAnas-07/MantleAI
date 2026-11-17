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
| Next | `chore/pin-dependencies` | Version ranges in `pyproject.toml` and a `requirements.lock` file, so every install is reproducible. |
| | `feat/database-models` | Alembic setup and the v0.1 tables from `docs/data-model.md`, with migration tests. |
| | `feat/llm-gateway` | Encrypted keys, model catalog, streaming chat and embeddings through LiteLLM, usage records, fake provider for tests. |
| | `feat/model-switching` | Conversations and streaming messages, context builder, rolling summary, handoff preview and switch. |

## [Phase 2: Project memory survives a switch](phases.md#phase-2-project-memory-survives-a-switch)

| Status | Branch | Goal |
| --- | --- | --- |
| | `feat/project-memory` | CRUD for requirements, decisions and tasks, fed into the context builder as pinned items. |

## [Phase 3: Answers that cite your code](phases.md#phase-3-answers-that-cite-your-code)

| Status | Branch | Goal |
| --- | --- | --- |
| | `feat/project-indexing-rag` | Index a local folder into pgvector, re-index only changed files, retrieve and cite top-k chunks in chat. |

## [Phase 4: Workflow, agents and teaching](phases.md#phase-4-workflow-agents-and-teaching)

| Status | Branch | Goal |
| --- | --- | --- |
| | `feat/workflow-and-agents` | Fixed workflow stages, Planner and Reviewer agents, approve, request changes or skip; approval of AI-proposed memory items. |
| | `feat/teaching-layer` | Project-aware "what, why, how" teaching notes on request, and the rule-based concepts list. |

## [Phase 5: Workspace UI (v0.1 complete)](phases.md#phase-5-workspace-ui-v01-complete)

| Status | Branch | Goal |
| --- | --- | --- |
| | `feat/frontend-workspace` | React + Vite + TS + Tailwind UI for everything above (design in `docs/design-app.md`). |

## [Phase 6: Safe execution, accounts and open-source release](phases.md#phase-6-safe-execution-accounts-and-open-source-release)

| Status | Branch | Goal |
| --- | --- | --- |
| | `feat/sandboxed-tool-execution` | Run approved commands in a locked-down Docker sandbox. |
| | `feat/authentication` | User accounts and sessions, so Mantle can run beyond one local user. |
| | `chore/ci-and-deployment` | GitHub Actions for lint and tests, a production build and deployment setup. |
| | `feat/landing-page` | Marketing landing page using `docs/design-landing.md` (after conflict C1 is resolved). |

## Later / ideas
