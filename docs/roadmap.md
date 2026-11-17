# Roadmap

Work happens in this order, one branch per item. The branch name follows the Git conventions in
`CLAUDE.md`. Items 1–9 make up v0.1 (see `docs/mvp-scope.md`); items 10–13 come after v0.1.

| # | Status | Branch | Goal |
| --- | --- | --- | --- |
| 1 | Done | `chore/project-scaffold` | Project setup: FastAPI skeleton, `/health`, Docker PostgreSQL, tooling. |
| 2 | Done | `docs/project-documentation` | Architecture, requirements, scope, data model, API outline, security, ADRs. |
| 3 | Next | `feat/database-models` | Alembic setup and the v0.1 tables from `docs/data-model.md`, with migration tests. |
| 4 | | `feat/llm-gateway` | Encrypted keys, model catalog, streaming chat and embeddings through LiteLLM, usage records, fake provider for tests. |
| 5 | | `feat/model-switching` | Conversations and streaming messages, context builder, handoff preview, switch with summary. |
| 6 | | `feat/project-indexing-rag` | Index a local folder into pgvector, re-index only changed files, retrieve and cite top-k chunks in chat. |
| 7 | | `feat/workflow-and-project-memory` | Memory items with approval, fixed workflow stages, Planner and Reviewer agents, approve, request changes or skip. |
| 8 | | `feat/teaching-layer` | Generate and store project-aware "what, why, how" teaching notes. |
| 9 | | `feat/frontend-workspace` | React + Vite + TS + Tailwind UI for everything above (design in `docs/design-app.md`). |
| 10 | | `feat/sandboxed-tool-execution` | Run approved commands in a locked-down Docker sandbox. |
| 11 | | `feat/authentication` | User accounts and sessions, so Mantle can run beyond one local user. |
| 12 | | `chore/ci-and-deployment` | GitHub Actions for lint and tests, a production build and deployment setup. |
| 13 | | `feat/landing-page` | Marketing landing page using `docs/design-landing.md` (after the conflicts are resolved). |

## Later / ideas
