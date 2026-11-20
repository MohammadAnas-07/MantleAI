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
  Flash -> Gemini 3.5 Flash Lite, both with all history verbatim and with decisions 1-3 reaching
  model B only through the rolling summary (`SUMMARY_TRIGGER_TOKENS=200`). Same provider only;
  a cross-provider run still needs a second working key. Run `python scripts/switch_demo.py --model-a ... --model-b ...` with real keys.
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
- [x] Requirements, decisions and tasks can be created, edited, given a status and deleted.
- [x] Active decisions and open tasks are added to every prompt as pinned items, inside the token budget.
- [ ] The "sources used" view lists the memory items that were sent. (Partly: the handoff preview and `GET /projects/{id}/memory/pinned` list them; per-message `MessageContext` rows and `GET /messages/{id}/context` are not built.)
- [ ] A new conversation with a different model passes the 5-question check from memory alone.
- [x] Memory items never go through vector search.

**Postponed:** AI-proposed memory items and their approval (Phase 4, done in
`feat/workflow-and-agents`), the workflow, agents.

## Phase 3: Answers that cite your code

**Goal:** Mantle answers questions about a real project's code, with sources.

**Branch:** `feat/project-indexing-rag`.

**Demo:** index the Mantle repo itself, ask "where is the health check timeout set?", and get an
answer that cites `backend/app/db/session.py` with line numbers. Switch models and ask again; the
citations still work.

**Exit criteria:**
- [x] Indexing a local folder works with an embedding key, and is refused without one (built and
  tested with FakeProvider on 2026-11-18; default model `gemini/gemini-embedding-001`; not yet
  run with a real key: `scripts/eval_retrieval.py`).
- [x] Secret files, binaries and large files are skipped, and the count is reported (per reason,
  with example paths, in the run's skip report and the documents list).
- [x] Re-indexing embeds only changed files (and only the changed segments in them).
- [ ] Answers cite real `path:lines`, and the "sources used" view lists them. (Partly: the prompt
  carries `<source path lines>` blocks, `message_start` lists the sources and `message_contexts`
  stores them; `GET /messages/{id}/context` and a real-model demo are not done.)
- [ ] The project profile (languages, dependencies, markers) is built without an LLM. Moved to
  its own branch, `feat/project-profile` (Phase 4, before `feat/teaching-layer`, which needs it).

**Also built:** hybrid search (vector + full text, reciprocal rank fusion), a cost estimate and
limit before indexing, resumable runs with rate-limit backoff, a per-conversation switch for
code context.

**Postponed:** reranker, external documentation, local embeddings, file watchers.

## Phase 4: Workflow, agents and teaching

**Goal:** structured engineering stages with human approval, and Mantle explains why.

**Branches:** `feat/workflow-and-agents`, `feat/project-profile`, `feat/teaching-layer`.

**Demo:** run the five stages for a small feature. The Planner drafts and the Reviewer flags
risks. Approving the agent run saves the chosen tasks (`todo`) and decisions (`proposed`) to
memory. Then ask "why did we choose this?" and get a teaching note.

**Exit criteria:**
- [x] The five stages run in order, each with approve, skip and reopen (reopen replaced
  request-changes on 2026-11-19; sending a plan back is "reject the run" with a reason).
  Backend in `feat/workflow-and-agents`; the workflow screen in `feat/workflow-ui`.
- [x] Planner and Reviewer produce text only and change nothing without approval (plain Python
  state machine, no LangGraph: ADR 0004). A gap finder lists missing steps and risks on request.
- [x] AI-proposed memory items stay `proposed` until you approve them (decisions are saved as
  `proposed`; you accept them in the memory panel).
- [ ] Teaching notes are created only on request; the concepts list uses rules only (no usage record).
- [ ] The demo above with a real model (`scripts/agent_demo.py` runs the Planner and Reviewer).

**Postponed:** more agents, LLM-based concept suggestions.

## Phase 5: Workspace UI (v0.1 complete)

**Goal:** everything above is usable in a browser, without the API docs page.

**Branch:** `feat/frontend-workspace`.

**Demo:** the full v0.1 flow in the React app: create a project, add memory, index it, chat,
switch models, approve a workflow stage, open a teaching note, check usage.

**Built so far** (`feat/frontend-workspace`, 2026-11-18): settings (keys, models, usage),
projects, the index panel, memory, conversations with streaming, the context preview, model
switching and the activity log. `feat/workflow-ui` (2026-11-20) adds the workflow page: stages
with gates and reasons, the gap finder, Planner and Reviewer runs with an estimate, live
status and the approval view, and agent badges in memory. The teaching screen comes with its
backend (Phase 4).

**Exit criteria:**
- [ ] Every "v0.1 is finished when" item in `docs/mvp-scope.md` is true. (Not yet: teaching
  needs Phase 4 first, and the workflow has not been run end to end with a real model.)
- [x] `docs/design-app.md` exists and the UI follows it.
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
