# MVP scope (v0.1)

v0.1 is a local tool for one developer on their own machine, using their own API keys.

## In v0.1

| Feature | What exactly |
| --- | --- |
| Single local user | No login. One default local user, and all data carries its `user_id`. The API binds to 127.0.0.1 only. |
| Bring your own API keys | OpenAI, Anthropic, Google and Voyage keys, stored encrypted in PostgreSQL. A "test key" button. Indexing needs an embeddings-capable key for the embedding model's provider (the default is Google's `gemini-embedding-001`; OpenAI and Voyage work too). |
| Projects and conversations in PostgreSQL | A project has many conversations, and a conversation has many messages. |
| Chat with streaming | Server-sent events, a cancel button, and errors shown clearly. |
| Model switching with context handoff | A rolling summary is built in the background by the utility model (default: the active model). Every one of these calls is logged and shown in the usage view, and background summaries can be turned off; then the summary is built at switch time. A switch carries the summary plus the recent messages that fit, after a preview, and never calls the old model. Every message is tagged with its model. |
| Project memory | Requirements, decisions and tasks (CRUD), fed into every prompt as pinned items. Built right after model switching (`feat/project-memory`). Items proposed by AI need approval, added with the workflow (`feat/workflow-and-agents`): drafts are saved only when the user approves a run, tasks as `todo` and decisions as `proposed`. |
| Project indexing with retrieval | Index a local folder, embed with the chosen embedding model (default `gemini/gemini-embedding-001`) into pgvector, find code with hybrid search (vector + full text), cite top-k sources as `path:lines`. Only changed files are re-indexed. Changing the embedding model means re-indexing. |
| Workflow stages with human approval | Requirements → Architecture → Technical decisions → Task breakdown → Implementation plan. Each one is approved (or approved anyway, with a reason), skipped with a reason, or reopened later by the user; a reset goes back to the first stage. There is no request-changes action and no revision loop: reopen replaces them (ADR 0004). A Planner draft is approved, in whole or in part, or rejected with a reason. |
| Two agents | Planner (drafts) and Reviewer (critiques), run in that order as a plain state machine in PostgreSQL, with no LangGraph (ADR 0004). A Reviewer-only run checks the current memory. No tools, text output only. |
| Gap finder | One model call on request that lists missing steps, risks, technical debt and scalability concerns for the current stage. It is not a third agent and proposes nothing to save. |
| Project profile (facts) | Languages, dependencies, manifests, frameworks, commands, layout and entry points, read from the files at the end of each successful index run with no LLM call, shown in a Profile tab and sent to the model as `<project_profile>`. A model-written profile summary is not built (`feat/profile-summary`). |
| Teaching notes (not built yet) | "What, why, how" notes, created only when the user asks, using project context (this is the only teaching LLM call). Plus a passive "concepts for this project" list, built by YAML rules and the project profile with no LLM call. No pop-ups or interruptions. |
| Visible background calls | Any LLM call the user did not directly ask for is logged, shown as its own line in the usage view, and can be turned off. In v0.1 the only one is the rolling summary. |
| Simple React UI | Projects, chat with a model picker, memory, workflow, teaching notes, settings. The first version (`feat/frontend-workspace`) has projects, chat, memory, index, context and settings; the workflow page came with `feat/workflow-ui` and the Profile tab with `feat/project-profile`. The teaching screen is not built; it waits for its backend. |

## Not in v0.1

| Out | Why it waits |
| --- | --- |
| Sandboxed code execution | Needs a safe sandbox design first (see `docs/security.md`). |
| GitHub integration | Local folders cover indexing for now. |
| Monaco editor | The UI is chat and panels first. Editing happens in the user's own IDE. |
| Redis and queues | In-process background tasks and PostgreSQL are enough for one user. |
| Multi-user auth | One local user (with `user_id` already on all data). Auth is its own roadmap item. |
| Hosted service | Not in v0.1. Revisit after the first demo; `user_id` and module boundaries keep it possible. |
| Local embedding model | A hosted embedding model through the gateway first (Gemini by default). |
| CI/CD integration | Comes after execution and GitHub. |
| Reranker | Hybrid search (vector + full text, rank fusion) first. Add a reranker once we can measure retrieval quality. |
| More than two agents | Prove Planner + Reviewer + human approval first. |

## v0.1 is finished when

1. A new user can follow `README.md`, add a key, create a project and chat with streaming.
2. They can switch from model A to model B in the middle of a conversation, and B answers at least
   4 of 5 questions about earlier decisions correctly (see `docs/prd.md`).
3. Decisions and tasks saved as project memory reach every model, even in a new conversation.
4. They can index a local folder and get answers that cite real `path:lines`.
5. They can run the workflow through each stage with Planner and Reviewer, approving each one.
6. They can create a teaching note from any message. (Not yet: the teaching layer is not built.)
7. All tests pass without API keys.
