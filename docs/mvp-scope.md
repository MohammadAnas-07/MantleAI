# MVP scope (v0.1)

v0.1 is a local tool for **one developer on their own machine**, using **their own API keys**.

## In v0.1

| Feature | What exactly |
| --- | --- |
| Single local user | No login. The API binds to 127.0.0.1 only. |
| Bring your own API keys | OpenAI, Anthropic and Google keys, stored encrypted in PostgreSQL. A "test key" button. |
| Projects and conversations in PostgreSQL | A project has many conversations, and a conversation has many messages. |
| Chat with streaming | Server-sent events, a cancel button, and errors shown clearly. |
| Model switching with context handoff | Preview what carries over. The target model summarises older history if it doesn't fit. Every message is tagged with its model. |
| Project indexing with retrieval | Index a local folder, embed into pgvector, cite top-k sources as `path:lines`. Only changed files are re-indexed. |
| Project memory | Requirements, decisions and tasks. Items proposed by AI need approval. |
| Workflow stages with human approval | Fixed stages. Each one is approved, sent back for changes, or skipped by the user. |
| Two agents | **Planner** (drafts) and **Reviewer** (critiques). No tools, text output only. |
| Teaching notes | "What, why, how" notes for a concept, a message or a stage, using project context. |
| Simple React UI | Projects, chat with a model picker, memory, workflow, teaching notes, settings. |

## Not in v0.1

| Out | Why it waits |
| --- | --- |
| Sandboxed code execution | Needs a safe sandbox design first (see `docs/security.md`). |
| GitHub integration | Local folders cover indexing for now. |
| Monaco editor | The UI is chat and panels first. Editing happens in the user's own IDE. |
| Redis and queues | In-process background tasks and PostgreSQL are enough for one user. |
| Multi-user auth | One local user. Auth is its own roadmap item. |
| CI/CD integration | Comes after execution and GitHub. |
| Reranker | Plain vector top-k first. Add one once we can measure retrieval quality. |
| More than two agents | Prove Planner + Reviewer + human approval first. |

## v0.1 is finished when

1. A new user can follow `README.md`, add a key, create a project and chat with streaming.
2. They can switch from model A to model B in the middle of a conversation, and B answers using
   the earlier context.
3. They can index a local folder and get answers that cite real `path:lines`.
4. They can run the workflow through each stage with Planner and Reviewer, approving each one.
5. They can create a teaching note from any message.
6. All tests pass without API keys.
