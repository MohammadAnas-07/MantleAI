# Idea

## The problem

When an LLM hits its limit in the middle of work, the developer has to start over somewhere else.
Today: *"When Claude's limit runs out, I copy the chat, paste it into ChatGPT, and spend about
10 minutes explaining the context again."* The copy loses the project's decisions, tasks,
architecture and the reasons behind the code.

## Who has it

First user: the author, a developer who builds software with several chat LLMs (Claude, ChatGPT)
and switches between them when limits, cost or quality force it. Next: other developers who work
the same way.

## The idea

Mantle is a local, open-source workspace where a developer's project lives outside any single LLM.
Its memory (decisions, tasks, architecture, conversation summary and indexed code) stays with the
project, so switching from one model to another mid-conversation continues the work instead of
restarting it. Mantle also explains why the code and decisions are the way they are, so the
developer learns instead of just copying output.

## Why existing tools are not enough

- Cursor, Cline, Continue and Aider are coding agents built around editing code. They support many
  models, and some have rules files or memory, but that memory is tied to their own editor and
  workflow. None of them puts a structured, human-approved project memory at the centre.
- Chat apps (ChatGPT, Claude) keep history per provider. Nothing carries over when you switch.
- Copy and paste works, but costs about 10 minutes per switch and drops older decisions.

## The differentiator

Project memory that survives a model switch. Decisions, tasks and architecture are stored as
structured, approved records, and Mantle can explain the reasons behind them. They belong to the
project, not to a model or a provider.

## Non-goals

Mantle will never be:

- An LLM, or a model host.
- A code editor or IDE replacement. Editing happens in your own editor.
- An autonomous agent that changes code or runs commands without human approval.
- A paid product. Mantle is open source (MIT) and unpaid; users pay only their own provider costs.

Not for now: a hosted service in v0.1. Revisit after the first demo. `user_id` on all data and
clean module boundaries keep hosting possible later; nothing is built for it now.

## Decisions

| Date | Decision |
| --- | --- |
| 2026-11-17 | License: MIT. No LICENSE file until the repository is public. |
| 2026-11-22 | MIT LICENSE file added before the repository is public (replaces the line above). |
| 2026-11-17 | Not a hosted service in v0.1; revisit after the first demo. |
| 2026-11-17 | Project memory is built right after model switching (Phase 2), because it's the differentiator. |

## Main risks

| Risk | Why it matters |
| --- | --- |
| Summaries lose important detail | If the next model misses a key decision, the core promise fails. |
| Existing tools add the same feature | Cursor and others could add cross-model memory. Mantle's edge must be the depth of project memory and the teaching, not only switching. |
| Too much scope for one part-time developer | `vision.md` is very wide; v0.1 must stay small (`docs/mvp-scope.md`). |
| Background LLM calls cost the user money | Handled by decision D10: logged, visible and possible to turn off. |
| The differentiator arrives late | Reduced: project memory now comes in Phase 2, right after model switching (`docs/phases.md`). |
| Someone sells a hosted copy | MIT allows it. Accepted for an open-source, unpaid project. |

## Weak points

- The success metric is self-measured. It has a testable part (at least 4 of 5 decision
  questions correct after each switch), but the author writes the questions and grades the
  answers.
- The differentiator against Cursor and Cline is a claim, not tested yet. Nobody has compared them
  side by side. Do one comparison before Phase 2 ends.
- There is only one user so far (the author). It's not yet known whether other developers share
  this pain.
