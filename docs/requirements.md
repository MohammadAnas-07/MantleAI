# Requirements

Each requirement is marked **MVP** (in v0.1) or **Later**. The scope rules are in
`docs/mvp-scope.md`.

## Functional

### Projects and memory
| ID | Requirement | Scope |
| --- | --- | --- |
| F-01 | Create, rename, archive and delete a project, with a name, a description and a local folder path. | MVP |
| F-02 | Store project memory items: requirements, decisions and tasks, each with a status. | MVP |
| F-03 | Agents and chat can *propose* memory items. A proposed item becomes active only after the user approves it. | MVP |
| F-04 | Track bugs, test results and development progress as memory items. | Later |

### LLM gateway and keys
| ID | Requirement | Scope |
| --- | --- | --- |
| F-10 | Add, test and delete API keys for OpenAI, Anthropic, Google and Voyage. Keys are stored encrypted. | MVP |
| F-11 | List the available models with their context window, and enable or disable them. | MVP |
| F-16 | Choose a **utility model** for background work such as rolling summaries. The default is the conversation's active model. | MVP |
| F-17 | Choose an embedding model. The default is a small OpenAI or Voyage model. This needs an embeddings-capable key. | MVP |
| F-12 | Record token usage and estimated cost for every LLM call. | MVP |
| F-13 | Map provider failures to clear error types (rate limit, context too long, auth, unavailable). | MVP |
| F-14 | Local and open-source models (for example via Ollama). | Later |
| F-15 | Usage limits and budgets per project. | Later |

### Conversations and model switching
| ID | Requirement | Scope |
| --- | --- | --- |
| F-20 | Create conversations inside a project and send messages. | MVP |
| F-21 | Stream assistant replies token by token (SSE). | MVP |
| F-22 | Every message records which model produced it. | MVP |
| F-23 | Switch the model in the middle of a conversation. Before confirming, the user sees what context will carry over. | MVP |
| F-24 | A rolling summary is built in the background as the conversation grows (using the utility model). A switch carries the summary plus the recent messages that fit, and never calls the old model. | MVP |
| F-25 | On a rate-limit or context-limit error, suggest switching models. Mantle never switches on its own. | MVP |
| F-26 | Show which sources and memory items were used for each answer. | MVP |
| F-27 | Automatic fallback model rules. | Later |

### RAG
| ID | Requirement | Scope |
| --- | --- | --- |
| F-30 | Index a local project folder: filter files, split them into chunks, embed and store them. | MVP |
| F-31 | Re-indexing only processes files that changed. | MVP |
| F-32 | Retrieve the top-k relevant chunks for a question and cite them as `path:lines`. | MVP |
| F-33 | Never index secret files (`.env`, keys) or binaries. | MVP |
| F-36 | Every chunk stores its embedding model name and dimension. Changing the embedding model means re-indexing the project. | MVP |
| F-37 | A local embedding model (no API key needed). | Later |
| F-34 | Reranker, hybrid keyword + vector search. | Later |
| F-35 | Index selected external documentation (URLs). | Later |

### Workflow and agents
| ID | Requirement | Scope |
| --- | --- | --- |
| F-40 | A project has a workflow with fixed stages, each with a status: Requirements → Architecture → Technical decisions → Task breakdown → Implementation plan. | MVP |
| F-41 | The Planner agent drafts a stage's output (for example requirements or a task breakdown). | MVP |
| F-42 | The Reviewer agent critiques a draft and lists risks, missing steps and technical debt. | MVP |
| F-43 | The user approves, requests changes to, or skips each stage. Nothing advances without approval. | MVP |
| F-44 | More agents (architecture, coding, testing, security, documentation). | Later |

### Teaching
| ID | Requirement | Scope |
| --- | --- | --- |
| F-50 | Generate a teaching note (what it is, why it matters here, how to do it) for a concept, a message or a stage, **only when the user asks**. | MVP |
| F-51 | Notes use the project's context, not generic text. | MVP |
| F-52 | A passive "concepts for this project" list in the teaching panel. It never interrupts the user (no pop-ups, nothing added to chat). | MVP |

### Execution and integrations
| ID | Requirement | Scope |
| --- | --- | --- |
| F-60 | Run tests and commands in a sandbox after approval. | Later |
| F-61 | GitHub integration, a Monaco editor, a terminal panel and CI/CD integration. | Later |
| F-62 | Multi-user accounts, login, workspaces and permissions. | Later |
| F-63 | All user data belongs to a user (`user_id`). v0.1 has one default local user. | MVP |

### UI
| ID | Requirement | Scope |
| --- | --- | --- |
| F-70 | A simple React UI with a project list, chat with a model picker, a memory panel, a workflow panel, teaching notes and key settings. | MVP |
| F-71 | An IDE-style layout (explorer, editor, bottom panel). | Later |

## Non-functional

| ID | Requirement | Scope |
| --- | --- | --- |
| N-01 | Runs locally on Windows with Python 3.12–3.14 and Docker Desktop. | MVP |
| N-02 | API keys are encrypted at rest, never returned by the API (only the last 4 characters), and never logged. | MVP |
| N-03 | The API and the database listen on 127.0.0.1 only. The API has strict CORS and Host checks. | MVP |
| N-13 | Every query on user data filters by `user_id`. | MVP |
| N-04 | The first streamed token reaches the UI within 300 ms of the provider sending it. | MVP |
| N-05 | `/health` answers within 2 s even when the database is down. | MVP |
| N-06 | Indexing a 2,000-file project finishes within 10 minutes and doesn't block chat. | MVP |
| N-07 | All tests run without API keys or network access. | MVP |
| N-08 | Modular monolith: modules depend only on each other's `service.py`, with no cycles. | MVP |
| N-09 | Every LLM call is logged with model, tokens, latency and status (not content). | MVP |
| N-10 | Database changes go through Alembic migrations. | MVP |
| N-11 | Tracing and metrics (OpenTelemetry, Prometheus). | Later |
| N-12 | Can grow from one local user to a multi-user server without a rewrite. | Later |
