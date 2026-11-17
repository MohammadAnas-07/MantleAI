# Product requirements (PRD)

Background: `docs/idea.md`. Scope: [`docs/mvp-scope.md`](mvp-scope.md). Requirement IDs:
[`docs/requirements.md`](requirements.md). Delivery order: [`docs/phases.md`](phases.md).

## Goal

Let a developer switch LLMs in the middle of real project work and keep going straight away, with
the project's decisions, tasks and reasons still there.

## Success metric

**Accepted 2026-11-17:**

> Over 2 weeks of using Mantle on a real project, at least **10 successful model switches**. A
> switch counts as successful only if work continues within **1 minute** with **no manual
> re-explaining**, **and** the new model answers **at least 4 of 5** decision questions
> correctly. Today's baseline is about 10 minutes per switch.

**Decision-question check (after every switch):** ask the new model 5 questions whose answers
depend on decisions made earlier in the same conversation (for example "Which database did we
choose, and why?"). Write the 5 questions and their expected answers down **before** the switch.
Mark each answer correct or wrong. Below 4 of 5, the switch is a failure, whatever the time.

How to measure: for each switch, log the time to the first useful answer, whether you
re-explained anything (yes/no), and the score out of 5. Usage records give the switch count.

## Target user

A developer (first: the author) who builds software with several chat LLMs, runs into limits, and
loses time and context when switching. Comfortable running a local Python app and Docker.

## User stories

### US-1: Switch models without starting over
As a developer whose model hit a limit, I want to switch to another model in the same
conversation, so that I keep working without copying and re-explaining.

Acceptance criteria:
- Given a conversation with model A, when I pick model B, a preview shows what will carry over
  (summary, recent messages, token count) before I confirm.
- After the switch, model B answers a question about a decision made earlier with A, without me
  restating it.
- Model A is never called during the switch, even if it's rate-limited.
- When A returns a rate-limit or context-limit error, Mantle suggests a switch and does not
  switch by itself.
- Every message shows the model that wrote it.

Needs: F-10, F-11, F-12, F-13, F-16, F-18, F-20, F-21, F-22, F-23, F-24, F-25, N-04, N-07.

### US-2: Project memory that outlives the model
As a developer, I want my project's requirements, decisions and tasks stored outside any model,
so that every model I use works from the same facts.

Acceptance criteria:
- I can add, edit and change the status of a requirement, decision or task.
- A memory item proposed by an AI stays `proposed` until I approve it.
- After a model switch, the new model's prompt contains the active decisions and open tasks, and
  the "sources used" view lists them.
- Memory items are never sent through vector search; they come from normal queries.

Needs: F-01, F-02, F-03, F-26, F-63.
Delivery: CRUD and pinned items in Phase 2 (`feat/project-memory`); approval of AI-proposed items
in Phase 4 (`feat/workflow-and-agents`).

### US-3: Ask about my code with real sources
As a developer, I want to ask questions about my own project and get answers that cite files and
lines, so that I can trust and check the answer.

Acceptance criteria:
- With an embeddings-capable key set, indexing a local folder finishes and reports files indexed
  and skipped.
- Without one, indexing is refused with a clear message.
- `.env`, key files and binaries are never indexed.
- An answer about the code cites at least one real `path:lines` that exists in the folder.
- Re-indexing an unchanged folder embeds nothing new.

Needs: F-17, F-30, F-31, F-32, F-33, F-36, F-53, N-06.

### US-4: Understand why
As a developer learning while I build, I want Mantle to explain the concepts and decisions behind
my project's code, so that I understand it instead of copying it.

Acceptance criteria:
- From any message I can ask for a teaching note, and it has "what", "why here" and "how"
  sections that mention my project.
- The "concepts for this project" list appears without any LLM call (usage shows no new record).
- Mantle never interrupts me with a teaching pop-up.

Needs: F-50, F-51, F-52, F-53, F-18.

### US-5: Work in stages with my approval
As a developer starting a feature, I want to move through requirements → architecture →
technical decisions → task breakdown → implementation plan, with a Planner and a Reviewer, so that
I don't skip engineering steps.

Acceptance criteria:
- The Planner drafts a stage, and the Reviewer lists risks and missing steps.
- A stage moves on only when I approve it; I can also request changes or skip it.
- Agents can't change anything by themselves; their output is text or proposed items.

Needs: F-03, F-40, F-41, F-42, F-43.

## Metrics

| Metric | Target | Source |
| --- | --- | --- |
| Time to continue after a switch | < 1 minute (baseline about 10) | Manual log during the 2-week trial |
| Decision questions answered correctly after a switch | ≥ 4 of 5 per switch | Manual log (questions written before the switch) |
| Successful switches | ≥ 10 in 2 weeks | Manual log + ContextHandoff rows |
| Answers citing a real file | ≥ 90% of code questions | Spot check of MessageContext |
| Background LLM cost | Visible on its own line; can be turned off | UsageRecord with `trigger = background` |

## Risks

See `docs/idea.md` → Main risks. Product-specific additions:

- The 2-week trial is run by the author alone, so the result may not hold for other developers.
- Phase 1 has no UI. The first demo runs through the API, which is harder to show to others.

## Answered (2026-11-17)

- Success metric: accepted, with the 5-question check (at least 4 of 5 correct).
- Time: 3 evenings per week. Dates are in `docs/phases.md`.
- License: MIT (no LICENSE file until the repo is public).
- Project memory: moved to Phase 2 (`feat/project-memory`), right after model switching.

## Open questions

1. F-03 says *chat* can also propose memory items. The workflow branch builds approval for agent
   proposals. Should proposals from ordinary chat replies be in v0.1, and in which branch?
