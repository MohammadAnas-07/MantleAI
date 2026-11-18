# Security

A basic threat model for v0.1: one user, running locally, using their own API keys.
`vision.md`'s rule applies everywhere: **never let an LLM freely execute commands on the host.**

## What we protect

- The user's provider API keys (they cost money and can be abused).
- The user's source code and project files.
- The user's machine.

## Who might attack

- Text that reaches the LLM from a file, web page or earlier message (prompt injection).
- Any website open in the user's browser, which can send requests to `localhost`.
- Other devices on the same network.
- Someone who gets a copy of the database, logs or repo.

## Risks

### 1. API key storage
| | |
| --- | --- |
| Risk | Keys leak from the database, API responses, logs or git. |
| MVP | Encrypt keys with Fernet using `MASTER_ENCRYPTION_KEY` from `backend/.env`, which is git-ignored. Without that key, a database dump is useless. The API never returns a key, only the last 4 characters. Keys are decrypted only inside the `llm` module, just before a call. `.env` is never committed. |
| Later | OS keychain (Windows Credential Manager) instead of a key in `.env`. Key rotation. Per-project key scopes and spend limits. |

### 2. Prompt injection
| | |
| --- | --- |
| Risk | Text in a file or message tells the model to ignore its instructions, leak data or take an action. |
| MVP | Agents and chat have **no tools** in v0.1. The worst result is bad text, never an action. Anything that changes state (memory items, stage approval) needs a human click. The system prompt says that retrieved content is data, not instructions. |
| Later | Tool-call authorization per tool, an allow-list of tools per agent, and checks on tool arguments before anything runs. |

### 3. Untrusted retrieved content
| | |
| --- | --- |
| Risk | Indexed files contain injection text, or secrets that get sent to a third-party LLM provider. |
| MVP | Every retrieved block goes in `<source path=... lines=...>` inside `<retrieved_context>`, with its citation. Text in the code that looks like our tags (`</source>`, `</retrieved_context>`, `</retrieved>`, ...) or a chat-template boundary (`<\|...\|>`, `[INST]`, `<<SYS>>`) is defanged (`<` becomes `&lt;`), and the system prompt says sources are data. Secrets are kept out as below. `message_start` lists exactly which sources were sent with each answer, and `message_contexts` stores their ids and line ranges. |
| Later | A `.mantleignore` file, a better secret scanner, and an option to block sending code to selected providers. |

#### What indexing skips, and why

Indexed text goes to a **third-party embedding provider** (Google by default), and every chat
message in an indexed project goes there as the search query. **Free tiers may use what they
receive for training.** The README says so where indexing is explained. So the rules are strict,
and a file that only looks risky is skipped whole: one file missing from the index is cheap, a
leaked key is not.

| Skipped | Why |
| --- | --- |
| Names: `.env`, `.env.*`, `*.env`, `*.pem`, `*.key`, `*.pfx`, `*.p12`, `*.jks`, `*.keystore`, `*.kdbx`, `id_*`, `credentials*`, `secrets*`, `.netrc`, `.npmrc`, `.pypirc`, `.htpasswd`, plus `INDEX_SENSITIVE_PATTERNS` | Files that usually hold keys or passwords. `id_*` follows rule 48 literally, so it also skips harmless files such as `id_utils.py`. Reason `sensitive_name` |
| Content with a private-key header, an AWS key id or secret, an OpenAI/Anthropic `sk-` key, a Google `AIza` key, a GitHub, Slack or Stripe live token | The whole file is skipped, reason `possible secret`. Only the reason and the path are stored |
| `.gitignore` matches (nested files and `!` negations), `.git`, `node_modules`, virtualenvs (any folder with `pyvenv.cfg`), `__pycache__`, `dist`, `build`, caches | Not the user's source, or already marked as private |
| Symlinks and Windows junctions | Never followed, so no link can leave the root and no loop can form |
| Lock files, minified files, source maps, images, archives, PDFs, fonts, media, compiled files, databases; any file with a null byte, a UTF-16/32 BOM or invalid UTF-8; lines over 10,000 characters | Binary or generated; nothing useful to embed |
| Files over `INDEX_MAX_FILE_BYTES` (1 MB), past `INDEX_MAX_FILES`, or with more than `INDEX_MAX_CHUNKS_PER_FILE` segments; files that change while read | Cost and correctness limits |

Logs from indexing and retrieval hold paths, counts, error codes and timings only, never file
contents or query text. An unexpected error is logged by its type name, because an exception
message could quote content.

### 4. File access
| | |
| --- | --- |
| Risk | Indexing reads files outside the project, or a path trick (`..`, symlinks) reaches system files. |
| MVP | Only `rag` reads files, and **only reads**. Mantle never writes to the project folder in v0.1. The root must be an absolute, readable folder, and can't be a filesystem root, the home folder or a folder above it; it is stored as its real path. Symlinks and junctions inside it are never followed. There are size limits (1 MB per file) and binary files are skipped. |
| Later | Per-project file permissions, and write access only through approved, sandboxed tools. |

### 5. Code execution
| | |
| --- | --- |
| Risk | An LLM runs a destructive or data-stealing command on the host. |
| MVP | **No code execution at all.** No module can run shell commands, and there is no execution endpoint. |
| Later | `feat/sandboxed-tool-execution`: run inside a Docker container with no network by default, the project mounted read-only plus a scratch folder, CPU, memory and time limits, a command allow-list, human approval for every command, and every run recorded in AuditEvent. |

### 6. Logs
| | |
| --- | --- |
| Risk | Keys, prompts or code end up in log files or tracebacks. |
| MVP | Log metadata only (model, tokens, latency, status, ids), never prompts, replies, keys or file contents. A logging filter masks anything that looks like a key or `Authorization` header. LiteLLM's verbose and debug logging stays off. `.env` and log files are git-ignored. |
| Later | Structured logs, a user setting for optional local prompt logging, and log retention limits. |

### 7. The local API is reachable by websites and the network
| | |
| --- | --- |
| Risk | There's no login in v0.1. Any web page in the browser could call `http://127.0.0.1:8000`, and other devices on the Wi-Fi could reach the API or the database. |
| MVP | uvicorn binds to `127.0.0.1` only. CORS allows only the frontend's dev origins (`CORS_ALLOWED_ORIGINS`, no wildcard, no credentials). A Host-header check (`ALLOWED_HOSTS`: localhost and 127.0.0.1 on any port) answers anything else with 400 `invalid_host`, which blocks DNS rebinding. **Done** in `feat/frontend-workspace`. Write requests must be JSON (which forces a CORS preflight). No GET request changes state. **Done (decision D6):** `docker-compose.yml` publishes the database on `127.0.0.1:5433` only (`fix/bind-database-to-localhost`). |
| Later | `feat/authentication`: real login and sessions, before Mantle is ever run on a server. Because every user-data table already has `user_id` and every query filters by it, auth only has to replace the "current user" dependency. |

### 8. Unrequested LLM calls (cost and data)
| | |
| --- | --- |
| Risk | Mantle quietly calls a paid model in the background. That spends the user's money and sends their content to a provider they didn't expect. |
| Rule | **Any LLM call the user did not directly ask for must be logged, visible, and possible to turn off.** |
| MVP | Every LLM call writes a UsageRecord with a `trigger` (`user` or `background`). The usage view shows each background purpose as its own line. The only background call in v0.1 is the rolling conversation summary, and it can be turned off (`background_summary_enabled`); when it's off, the summary is built at switch time, which the user asked for. The concepts list uses rules only, with no LLM. Indexing embeddings start from the user's index request; the query embedding of a chat message starts from the message. Both are logged with purpose `embedding`, and the query embedding can be turned off per conversation (`code_context_enabled`). Indexing has a cost guard: an estimate runs first and indexing above `INDEX_COST_LIMIT_USD` needs `force` (an app setting in v0.1; it moves to user settings when auth arrives). |
| Later | Spending caps for background calls, and a per-project switch. |

## Checklist for every PR

- No secret in code, tests, fixtures or logs.
- No new way for an LLM output to trigger an action without human approval.
- No new file access outside `rag`, and no writes.
- Every new query on user data filters by `user_id`.
- No new LLM call the user didn't directly ask for, unless it's logged, visible and can be turned off.
