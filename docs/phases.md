# Phases

Each phase ends with a demo you can show. Branches per phase are in [`docs/roadmap.md`](roadmap.md).
v0.1 (`docs/mvp-scope.md`) is complete at the end of Phase 5.

## Time estimate

- One feature branch takes 2–4 evenings; `chore/pin-dependencies` about 1 evening.
- **3 evenings per week** (confirmed 2026-11-17), so a feature branch takes about 1 week.
- Dates count from 2026-11-17. The range is "every branch takes 2 evenings" to "every branch takes
  4 evenings". The **target** is the later date.

| Phase | Demo | Earliest | Target |
| --- | --- | --- | --- |
| 1 | Switch models without losing context | 2026-12-03 | **2026-12-17** |
| 2 | Project memory survives a switch | 2026-12-08 | **2026-12-27** |
| 3 | Answers that cite your code | 2026-12-13 | **2027-01-05** |
| 4 | Workflow, agents and teaching | 2026-12-22 | **2027-01-24** |
| 5 | Workspace UI (v0.1 complete) | 2026-12-27 | **2027-02-02** |
| 6 | Safe execution, accounts, release | not dated | after v0.1 |

The UI branch is likely to take more than 4 evenings, so treat the Phase 5 date as optimistic.

## How every switch is judged

A model switch counts as **successful** only if work continues within 1 minute, with no manual
re-explaining, and the new model answers **at least 4 of 5** decision questions correctly. The 5
questions depend on decisions made earlier in the same conversation, and are written down with
their expected answers before the switch. (Success metric: `docs/prd.md`.)

## Phase 1: Switch models without losing context

**Goal:** the core feature works end to end. You switch models in the middle of a conversation,
and the new model continues with the earlier context.

**Branches left:** `chore/pin-dependencies`, `feat/database-models`, `feat/llm-gateway`,
`feat/model-switching`.

**Demo** (in `/docs` or a short PowerShell script):
1. Add a Claude key and an OpenAI key.
2. Chat with Claude about a small design and make a few decisions, with streamed replies.
3. Write down 5 decision questions with their expected answers.
4. Look at the handoff preview for GPT, then switch.
5. Ask GPT the 5 questions. At least 4 must be correct, with nothing re-explained.
6. Show the usage list: each call, its model, and background summary calls on their own line.

**Exit criteria:**
- [x] Dependencies have version ranges, and `backend/requirements.lock` exists.
- [x] Alembic migrations create all v0.1 tables and downgrade cleanly; the seed script creates the default local user.
- [x] Keys are stored encrypted; the API shows only the last 4 characters.
- [ ] Streaming chat works with at least two providers. (Built and tested with FakeProvider; not yet run against real providers.)
- [x] Every message records its model, and every LLM call writes a usage record with `trigger`.
- [x] The rolling summary runs in the background and can be turned off; when off, the summary is built at switch time.
- [x] The handoff preview shows what carries over; the switch never calls the old model.
- [x] A rate-limit or context-limit error shows a "switch model" suggestion.
- [x] The demo switch passes the 5-question check (at least 4 of 5): 5/5 on 2026-11-18, Gemini 3.8
  Flash -> Gemini 3.5 Flash Lite (same provider, summary not exercised). Run `python scripts/switch_demo.py --model-a ... --model-b ...` with real keys.
- [x] All tests pass without API keys.

**Postponed:** any UI, project memory, indexing, workflow, teaching.

## Phase 2: Project memory survives a switch

**Goal:** the differentiator. Requirements, decisions and tasks live in the project, not in the
conversation, and every model sees them.

**Branch:** `feat/project-memory`: CRUD for requirements, decisions and tasks, fed into the
context builder as pinned items.

**Demo:** record 3 decisions and 2 open tasks as memory. Start a **new** conversation with a
different model and ask the 5 decision questions. It answers from memory, with no conversation
history to rely on, and the "sources used" view lists the memory items.

**Exit criteria:**
- [ ] Requirements, decisions and tasks can be created, edited, given a status and deleted.
- [ ] Active decisions and open tasks are added to every prompt as pinned items, inside the token budget.
- [ ] The "sources used" view lists the memory items that were sent.
- [ ] A new conversation with a different model passes the 5-question check from memory alone.
- [ ] Memory items never go through vector search.

**Postponed:** AI-proposed memory items and their approval (Phase 4), the workflow, agents.

## Phase 3: Answers that cite your code

**Goal:** Mantle answers questions about a real project's code, with sources.

**Branch:** `feat/project-indexing-rag`.

**Demo:** index the Mantle repo itself, ask "where is the health check timeout set?", and get an
answer that cites `backend/app/db/session.py` with line numbers. Switch models and ask again; the
citations still work.

**Exit criteria:**
- [ ] Indexing a local folder works with an OpenAI or Voyage embedding key, and is refused without one.
- [ ] Secret files, binaries and large files are skipped, and the count is reported.
- [ ] Re-indexing embeds only changed files.
- [ ] Answers cite real `path:lines`, and the "sources used" view lists them.
- [ ] The project profile (languages, dependencies, markers) is built without an LLM.

**Postponed:** reranker, hybrid search, external documentation, local embeddings.

## Phase 4: Workflow, agents and teaching

**Goal:** structured engineering stages with human approval, and Mantle explains why.

**Branches:** `feat/workflow-and-agents`, `feat/teaching-layer`.

**Demo:** run the five stages for a small feature. The Planner drafts and the Reviewer flags
risks. Approving a stage turns its proposed decisions into memory. Then ask "why did we choose
this?" and get a teaching note.

**Exit criteria:**
- [ ] The five stages run in order, each with approve, request-changes and skip.
- [ ] Planner and Reviewer produce text only and change nothing without approval.
- [ ] AI-proposed memory items stay `proposed` until you approve them.
- [ ] Teaching notes are created only on request; the concepts list uses rules only (no usage record).

**Postponed:** more agents, LLM-based concept suggestions.

## Phase 5: Workspace UI (v0.1 complete)

**Goal:** everything above is usable in a browser, without the API docs page.

**Branch:** `feat/frontend-workspace`.

**Demo:** the full v0.1 flow in the React app: create a project, add memory, index it, chat,
switch models, approve a workflow stage, open a teaching note, check usage.

**Exit criteria:**
- [ ] Every "v0.1 is finished when" item in `docs/mvp-scope.md` is true.
- [ ] `docs/design-app.md` exists and the UI follows it.
- [ ] A new user can go from `README.md` to a first chat in under 15 minutes.
- [ ] You start the 2-week trial for the success metric in `docs/prd.md`.

**Postponed:** Monaco editor, IDE-style layout, landing page.

## Phase 6: Safe execution, accounts and open-source release

**Goal:** after v0.1, Mantle can run approved commands safely, supports more than one user, and
is ready for other developers.

**Branches:** `feat/sandboxed-tool-execution`, `feat/authentication`, `chore/ci-and-deployment`,
`feat/landing-page`.

**Demo:** the Reviewer suggests running the tests; you approve; they run in a locked-down
container. A second user logs in and sees only their own projects. The public repo has a green CI
badge, a LICENSE file and a landing page.

**Exit criteria:**
- [ ] Commands run only in a sandbox (no network, resource limits), and each one needs approval.
- [ ] Every execution is recorded in the audit log.
- [ ] Login works, and no query returns another user's data.
- [ ] CI runs lint and tests on every pull request.
- [ ] The repo is public, with an MIT LICENSE file.
- [ ] The landing page is live, with conflict C1 resolved.

**Postponed:** hosted version (decide after the first demo), GitHub integration, a terminal
panel, Redis and queues.
