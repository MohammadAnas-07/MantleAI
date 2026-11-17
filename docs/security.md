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
| MVP | Every chunk goes in delimited blocks (`<source path=... lines=...>`), with its citation. Secret files are never indexed: `.env*`, `*.pem`, `*.key`, `id_*`, `*.pfx`. Chunks that look like keys (private-key headers, `sk-`/`AKIA` style tokens) are dropped. The UI shows exactly which sources were sent with each answer. |
| Later | A configurable ignore file (`.mantleignore`), a better secret scanner, and an option to block sending code to selected providers. |

### 4. File access
| | |
| --- | --- |
| Risk | Indexing reads files outside the project, or a path trick (`..`, symlinks) reaches system files. |
| MVP | Only `rag` reads files, and **only reads**. Mantle never writes to the project folder in v0.1. Every path is resolved and must stay inside `root_path`; symlinks that point outside are skipped. There are size limits (1 MB per file) and binary files are skipped. |
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
| MVP | uvicorn binds to `127.0.0.1` only. CORS allows only the frontend's dev origin. A Host-header check (localhost / 127.0.0.1 only) blocks DNS-rebinding. Write requests must be JSON (which forces a CORS preflight). No GET request changes state. **Follow-up (decision D6):** `docker-compose.yml` currently publishes the database on all interfaces. Branch `fix/bind-database-to-localhost` changes it to `127.0.0.1:5433:5432`. |
| Later | `feat/authentication`: real login and sessions, before Mantle is ever run on a server. Because every user-data table already has `user_id` and every query filters by it, auth only has to replace the "current user" dependency. |

### 8. Unrequested LLM calls (cost and data)
| | |
| --- | --- |
| Risk | Mantle quietly calls a paid model in the background. That spends the user's money and sends their content to a provider they didn't expect. |
| Rule | **Any LLM call the user did not directly ask for must be logged, visible, and possible to turn off.** |
| MVP | Every LLM call writes a UsageRecord with a `trigger` (`user` or `background`). The usage view shows each background purpose as its own line. The only background call in v0.1 is the rolling conversation summary, and it can be turned off (`background_summary_enabled`); when it's off, the summary is built at switch time, which the user asked for. The concepts list uses rules only, with no LLM. |
| Later | Spending caps for background calls, and a per-project switch. |

## Checklist for every PR

- No secret in code, tests, fixtures or logs.
- No new way for an LLM output to trigger an action without human approval.
- No new file access outside `rag`, and no writes.
- Every new query on user data filters by `user_id`.
- No new LLM call the user didn't directly ask for, unless it's logged, visible and can be turned off.
