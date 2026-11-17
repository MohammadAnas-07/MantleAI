# Roadmap

Work happens in this order, one branch per item. Branch names follow the Git conventions in
`CLAUDE.md`. Items are grouped by phase; goals, demos and exit criteria are in
[`docs/phases.md`](phases.md). Phases 1–4 make up v0.1 (see `docs/mvp-scope.md`).

## [Phase 1: Switch models without losing context](phases.md#phase-1-switch-models-without-losing-context)

| Status | Branch | Goal |
| --- | --- | --- |
| Done | `chore/project-scaffold` | Project setup: FastAPI skeleton, `/health`, Docker PostgreSQL, tooling. |
| Done | `docs/project-documentation` | Architecture, requirements, scope, data model, API outline, security, ADRs. |
| Done | `fix/bind-database-to-localhost` | Publish PostgreSQL on 127.0.0.1 only. |
| Done | `docs/product-and-process-docs` | Idea, PRD, rules, phases and working memory. |
| Next | `feat/database-models` | Alembic setup and the v0.1 tables from `docs/data-model.md`, with migration tests. |
| | `feat/llm-gateway` | Encrypted keys, model catalog, streaming chat and embeddings through LiteLLM, usage records, fake provider for tests. |
| | `feat/model-switching` | Conversations and streaming messages, context builder, rolling summary, handoff preview and switch. |

## [Phase 2: Project-aware answers](phases.md#phase-2-project-aware-answers)

| Status | Branch | Goal |
| --- | --- | --- |
| | `feat/project-indexing-rag` | Index a local folder into pgvector, re-index only changed files, retrieve and cite top-k chunks in chat. |

## [Phase 3: Project memory, workflow and teaching](phases.md#phase-3-project-memory-workflow-and-teaching)

| Status | Branch | Goal |
| --- | --- | --- |
| | `feat/workflow-and-project-memory` | Memory items with approval, fixed workflow stages, Planner and Reviewer agents, approve, request changes or skip. |
| | `feat/teaching-layer` | Project-aware "what, why, how" teaching notes on request, and the rule-based concepts list. |

## [Phase 4: Workspace UI (v0.1 complete)](phases.md#phase-4-workspace-ui-v01-complete)

| Status | Branch | Goal |
| --- | --- | --- |
| | `feat/frontend-workspace` | React + Vite + TS + Tailwind UI for everything above (design in `docs/design-app.md`). |

## [Phase 5: Safe execution and accounts](phases.md#phase-5-safe-execution-and-accounts)

| Status | Branch | Goal |
| --- | --- | --- |
| | `feat/sandboxed-tool-execution` | Run approved commands in a locked-down Docker sandbox. |
| | `feat/authentication` | User accounts and sessions, so Mantle can run beyond one local user. |

## [Phase 6: Open-source release](phases.md#phase-6-open-source-release)

| Status | Branch | Goal |
| --- | --- | --- |
| | `chore/ci-and-deployment` | GitHub Actions for lint and tests, a production build and deployment setup. |
| | `feat/landing-page` | Marketing landing page using `docs/design-landing.md` (after conflict C1 is resolved). |

## Later / ideas
