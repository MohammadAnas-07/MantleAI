# Phases

Each phase ends with a demo you can show. Branches per phase are in [`docs/roadmap.md`](roadmap.md).
v0.1 (`docs/mvp-scope.md`) is complete at the end of Phase 4.

**Time estimate:** one branch takes 2–4 evenings. Assuming **3 evenings a week** (not confirmed),
a branch takes about 1 week.

## Phase 1: Switch models without losing context

**Goal:** the core feature works end to end. You switch models in the middle of a conversation,
and the new model continues with the earlier context.

**Branches left:** 3 (`feat/database-models`, `feat/llm-gateway`, `feat/model-switching`).
**Target demo:** 2026-12-15 (range 2026-12-01 to 2026-12-15).

**Demo:** in the API docs page (`/docs`) or a short PowerShell script:
1. Add a Claude key and an OpenAI key.
2. Chat with Claude about a small design decision for several messages, with streamed replies.
3. Look at the handoff preview for GPT, then switch.
4. Ask GPT "what did we decide earlier, and why?" It answers correctly without being told again.
5. Show the usage list: each call, its model, and the background summary calls on their own line.

**Exit criteria:**
- [ ] Alembic migrations create all v0.1 tables and the default local user, and downgrade cleanly.
- [ ] Keys are stored encrypted; the API shows only the last 4 characters.
- [ ] Streaming chat works with at least two providers.
- [ ] Every message records its model, and every LLM call writes a usage record with `trigger`.
- [ ] The rolling summary runs in the background and can be turned off; when off, the summary is built at switch time.
- [ ] The handoff preview shows what carries over; the switch never calls the old model.
- [ ] A rate-limit or context-limit error shows a "switch model" suggestion.
- [ ] All tests pass without API keys.

**Postponed:** any UI, project indexing, project memory, workflow, teaching.

## Phase 2: Project-aware answers

**Goal:** Mantle answers questions about a real project's code, with sources.

**Demo:** index the Mantle repo itself, ask "where is the health check timeout set?", and get an
answer that cites `backend/app/db/session.py` with line numbers. Then switch models and ask again;
the citations still work.

**Exit criteria:**
- [ ] Indexing a local folder works with an OpenAI or Voyage embedding key, and is refused without one.
- [ ] Secret files, binaries and large files are skipped, and the count is reported.
- [ ] Re-indexing embeds only changed files.
- [ ] Answers cite real `path:lines`, and the "sources used" view lists them.
- [ ] The project profile (languages, dependencies, markers) is built without an LLM.

**Postponed:** reranker, hybrid search, external documentation, local embeddings.

## Phase 3: Project memory, workflow and teaching

**Goal:** the differentiator. Project memory and reasons survive model switches, and Mantle
explains why.

**Demo:** run the workflow for a small feature. The Planner drafts requirements and the Reviewer
flags risks. You approve, and decisions become memory. Switch models, and the new model works
from those decisions. Ask "why did we choose this?" and get a teaching note.

**Exit criteria:**
- [ ] Requirements, decisions and tasks can be created, edited and approved; AI proposals stay `proposed` until approved.
- [ ] The five stages run in order, each with approve, request-changes and skip.
- [ ] Planner and Reviewer produce text only and change nothing without approval.
- [ ] After a switch, active decisions and open tasks are in the new model's context.
- [ ] Teaching notes are created on request; the concepts list uses rules only (no usage record).

**Postponed:** more agents, automatic concept suggestions with an LLM.

## Phase 4: Workspace UI (v0.1 complete)

**Goal:** everything above is usable in a browser, without the API docs page.

**Demo:** the full v0.1 flow in the React app: create a project, index it, chat, switch models,
approve a workflow stage, open a teaching note, check usage.

**Exit criteria:**
- [ ] Every "v0.1 is finished when" item in `docs/mvp-scope.md` is true.
- [ ] `docs/design-app.md` exists and the UI follows it.
- [ ] A new user can go from `README.md` to a first chat in under 15 minutes.
- [ ] You start the 2-week trial for the success metric in `docs/prd.md`.

**Postponed:** Monaco editor, IDE-style layout, landing page.

## Phase 5: Safe execution and accounts

**Goal:** Mantle can run approved commands safely, and is ready for more than one user.

**Demo:** the Reviewer suggests running the tests; you approve; they run in a locked-down container
and the output appears in the conversation. A second user logs in and sees only their own projects.

**Exit criteria:**
- [ ] Commands run only in a sandbox (no network, resource limits), and each one needs approval.
- [ ] Every execution is recorded in the audit log.
- [ ] Login works, and no query returns another user's data.

**Postponed:** GitHub integration, a terminal panel.

## Phase 6: Open-source release

**Goal:** other developers can find, install and trust Mantle.

**Demo:** a public landing page, a green CI badge, and a tagged release that installs from the
README on a clean Windows machine.

**Exit criteria:**
- [ ] CI runs lint and tests on every pull request.
- [ ] A license file is in the repo.
- [ ] The landing page is live, with conflict C1 resolved.

**Postponed:** hosted version, Redis and queues, CI/CD integration inside Mantle.
