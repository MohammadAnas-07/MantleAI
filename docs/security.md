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
| Wrong or changed master key | A missing or malformed `MASTER_ENCRYPTION_KEY` stops the app at startup. A valid key that differs from the one the provider keys were saved with is reported, not hidden: calls fail with `credential_unreadable` (restore the previous master key, or enter the key again), `/health` says `keys: unreadable` and the UI shows a banner, the credentials list marks each unreadable key, and startup logs a count. Nothing is printed except a count and provider names in the UI; saved keys are never changed or deleted automatically, and a key entered again is saved as a new row through the normal path. |
| Later | OS keychain (Windows Credential Manager) instead of a key in `.env`. Key rotation. Per-project key scopes and spend limits. |

### 2. Prompt injection
| | |
| --- | --- |
| Risk | Text in a file or message tells the model to ignore its instructions, leak data or take an action. |
| MVP | Agents and chat have **no tools** in v0.1. The worst result is bad text, never an action. Anything that changes state (memory items, stage approval) needs a human click. The system prompt says that retrieved content is data, not instructions. |
| Agents (`feat/workflow-and-agents`) | The gap finder, Planner and Reviewer get memory, the requirement, a draft plan and optional code inside tags (`<project>`, `<stage>`, `<project_memory>`, `<requirement>`, `<plan>`, `<retrieved_context>`), with those tags and chat-template markers defanged by `app/core/prompt_data.py`. Their prompts say that data is never an instruction. Their output is parsed as JSON and validated with Pydantic: unknown fields are dropped, ids are checked against the project (unknown ones removed, with a warning), plans are checked for size, valid dependencies and cycles. The result is a draft: it changes no memory, stage or status. Only `POST /agent-runs/{id}/approve` saves items, through the same checks as manual input, as tasks `todo` and decisions `proposed`. Stage changes have no model involvement at all. Nothing in model output is ever executed or followed. Logs hold ids, counts, tokens and timings only. Runs are refused above `AGENT_RUN_COST_LIMIT_USD` without `force`, and on a model with no price at all unless `AGENT_ALLOW_UNPRICED_MODELS=true` (fail closed). |
| Chat prompts | Every prompt builder uses one helper (`app/core/prompt_data.py`, `defang`) on everything it did not write itself, and puts it inside a tag: pinned memory (`<pinned_items>`), the rolling summary (`<conversation_summary>`), retrieved code (`<source>` in `<retrieved_context>`, paths and symbols as escaped attributes), and the project name and description. The rolling-summary prompt defangs the messages it summarizes and the previous summary (`<new_messages>`, `<previous_summary>`), so a pasted `</new_messages>` or a chat-template marker can't steer the summary every later prompt reuses. Tests feed closing tags, "ignore previous instructions", fake system turns and image links with data in the URL, and check that a hostile chat reply or gap finder answer changes no memory item and no workflow state. |
| Rendering in the browser | Model output, memory and agent drafts are untrusted. Chat replies go through `Markdown.tsx`: raw HTML is dropped; images are never loaded (the alt text and the address are shown as text, because fetching one could send data to its server); a link becomes clickable only for an absolute `http`, `https` or `mailto` address, opens in a new tab with `rel="noopener noreferrer"` and shows its real target; anything else (`javascript:`, `data:`, `file:`, relative and fragment links) is plain text. Everything else (memory, gap finder, Planner and Reviewer text) is plain React text. Lint refuses `dangerouslySetInnerHTML`. The built app (`npm run build`, `npm run preview`) carries a Content-Security-Policy meta tag: `default-src 'self'`, no remote images (`img-src 'self' data:`), scripts only from the app, no frames or plugins, requests only to the app and the API origin. **Limit:** `npm run dev` has no CSP, because Vite's hot reload needs inline scripts; a meta tag can't set `frame-ancestors`, so other sites could still frame the built page (a server header would be needed). |
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
| Names (checked before any content is read): environment files `.env`, `.env.*`, `*.env`, `.envrc`; keys and certificates `*.pem`, `*.key`, `*.crt`, `*.cer`, `*.der`, `*.p7b`, `*.p7c`, `*.pfx`, `*.p12`, `*.jks`, `*.keystore`, `*.kdbx`, `*.ppk`, `*.gpg`, `id_*`; credential files `credentials*`, `*credentials.json`, `service-account*.json`, `service_account*.json`, `serviceaccount*.json`, `secrets*`, `.netrc`, `.npmrc`, `.pypirc`, `.htpasswd`, `.git-credentials`, `.pgpass`, `.my.cnf`, `local.settings.json`, `wp-config.php`; cloud and cluster config `.aws/config`, `.docker/config.json`, `.dockercfg`, `kubeconfig`, `*.kubeconfig`, `.kube/config`, `*.ovpn`; terraform `*.tfvars`, `*.tfvars.json`, `*.tfstate`, `*.tfstate.*`; plus `INDEX_SENSITIVE_PATTERNS` | Files that usually hold keys or passwords. `id_*` follows rule 48 literally, so it also skips harmless files such as `id_utils.py`; `credentials*` also skips a `credentials-guide.md`. Reason `sensitive_name` |
| Content (`app/modules/rag/secret_scan.py`): (1) known formats: private-key blocks (PEM, OpenSSH, PGP, PuTTY), AWS key ids, `sk-` keys (OpenAI and Anthropic style), Google `AIza` keys and `GOCSPX-` OAuth secrets, GitHub `gh?_` and `github_pat_`, GitLab `glpat-`, Slack tokens and webhook URLs, Stripe `sk_`/`rk_` live and test keys and `whsec_`, Hugging Face `hf_`, npm `npm_`, SendGrid `SG.`, PyPI tokens, Azure `AccountKey=`, signed JWTs; (2) connection strings with a password for postgres, mysql, mariadb, mongodb, redis, amqp, mssql and oracle; (3) assignments: a name ending in a secret word (`password`, `passwd`, `pwd`, `passphrase`, `secret`, `token`, `apikey`, `credential(s)`, or `<api/access/secret/private/client/auth/encryption/signing/master/...>_key`, in snake, kebab or camel case) given a literal value: quoted values in any file, bare values too in config files (YAML, TOML, INI, JSON, XML, `.properties`, `.tf`, `.hcl`, `.env`-style, docker-compose, Dockerfile), including inside `Server=...;Password=...;` strings; and any other `*_key` name with a value of 20 or more characters, mixed case or digits, high entropy, not a hex digest or UUID | The whole file is skipped, reason `possible secret`, before it is split. Nothing of it is stored except the path, reason and size on its document row, and the run's skip report keeps only a count for `possible secret` and `sensitive_name` (no paths). The result is a yes or no; what matched is never returned, stored or logged |
| `.gitignore` matches (nested files and `!` negations), `.git`, `node_modules`, virtualenvs (any folder with `pyvenv.cfg`), `__pycache__`, `dist`, `build`, caches | Not the user's source, or already marked as private |
| Symlinks and Windows junctions | Never followed, so no link can leave the root and no loop can form |
| Lock files, minified files, source maps, images, archives, PDFs, fonts, media, compiled files, databases; any file with a null byte, a UTF-16/32 BOM or invalid UTF-8; lines over 10,000 characters | Binary or generated; nothing useful to embed |
| Files over `INDEX_MAX_FILE_BYTES` (1 MB), past `INDEX_MAX_FILES`, or with more than `INDEX_MAX_CHUNKS_PER_FILE` segments; files that change while read | Cost and correctness limits |

**Not skipped on purpose (false-positive trade-offs).** Placeholders (`your-key-here`,
`<...>`, `${VAR}`, `{{ var }}`, `changeme`, `example`, `xxxx`), references (`os.environ[...]`,
`process.env.X`, `settings.x`), empty values, type annotations, JSON schemas, numbers, hex
digests, UUIDs, base64 images and lock-file hashes. A bare `key` name (React and dictionary
keys) and a lowercase identifier value don't count. A local connection string whose password
equals its user name (`postgres:postgres@localhost`) is a dev default and doesn't count. The
other way round, test files with fake keys and a docker-compose file with a real dev password
are skipped: on Mantle's own repository that is 13 test files and `docker-compose.yml` of 320.

**What pattern matching can't catch.** A secret under a neutral name (`db_conn = "hunter2"`,
`CONFIG = {"pw": ...}` with an unknown key), a password split across lines or built at runtime,
a bare value in a code file (`PASSWORD = hunter2` in a shell script is caught only if the file
type counts as config), a secret shorter than the minimum length (6 for passwords, 8 for
tokens), unknown token formats, secrets in file types that are read but not listed as config
(for example a `.go` constant with a neutral name). Keep secrets out of the repository, use
`.gitignore` or `INDEX_SENSITIVE_PATTERNS` for anything else private, and treat this scanner as
a safety net.

**Rule changes reach old data.** Each document records the rules version it was checked with
(`documents.scan_version`, `secret_scan.RULES_VERSION`). After a rules change, the next index
run reads every indexed file again (no embedding call unless the text changed); a file that now
counts as a secret, or whose name is now sensitive, loses its stored segments and embeddings.
Text that already went to the embedding provider, or into earlier chat replies and summaries,
can't be recalled: rotate any key that was indexed.

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
| Risk | Keys, prompts, message text, memory or code end up in log files or tracebacks. |
| MVP | **Logged:** event names, ids, counts, token numbers, latency, status, stable error codes and exception type names; the route of an unhandled error; per model call one line `llm call model=... purpose=... trigger=... status=... error=... input_tokens=... output_tokens=... latency_ms=...`. **Never logged:** prompts, replies, message text, memory text, file contents or file paths from an index, keys, ciphertext, the master key, the database password, `Authorization` headers, provider error text and exception messages (they can quote any of these). At the source: error paths log `type(exc).__name__` only; provider errors are logged as type, HTTP status and the sanitized `usage_records.error_detail` fields; request validation errors drop the input; the SQL engine runs with `hide_parameters=True`; settings print no secret (`repr=False`); an unknown error is answered as `internal_error` and logged by type. **Second line:** a filter on the root and uvicorn handlers masks key shapes, Fernet tokens, `Authorization`/`api_key`/`password`/`MASTER_ENCRYPTION_KEY` assignments and SQL `[parameters: ...]`, in messages and in formatted tracebacks. **Limit:** PostgreSQL's own error text can quote a bad value, which is why exception messages are never logged. Stored error fields (`messages.error_code`, `usage_records.error_code` and `error_detail`, run `error` and `error_message`) hold codes and our own sentences, never exception text. Sentinel tests force each failure path and check that a marker in a message, memory item, file path, file content or key appears in no log line and no stored error. LiteLLM's verbose and debug logging stays off. `.env` is git-ignored. |
| Later | Structured (JSON) logs with request ids, a user setting for optional local prompt logging, and log retention limits. |

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
