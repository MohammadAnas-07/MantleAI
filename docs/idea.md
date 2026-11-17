# Idea

## The problem

When an LLM hits its limit in the middle of work, the developer has to start over somewhere else.
Today: *"When Claude's limit runs out, I copy the chat, paste it into ChatGPT, and spend about
10 minutes explaining the context again."* What gets lost is exactly what matters most: the
project's decisions, tasks, architecture and the reasons behind the code.

## Who has it

First user: **the author**, a developer who builds software with several chat LLMs (Claude,
ChatGPT) and switches between them when limits, cost or quality force it. Next: other developers
who work the same way.

## The idea in 3 sentences

Mantle is a local, open-source workspace where a developer's project lives outside any single LLM.
Its memory (decisions, tasks, architecture, conversation summary and indexed code) stays with the
project, so switching from one model to another mid-conversation continues the work instead of
restarting it. Mantle also explains *why* the code and decisions are the way they are, so the
developer learns instead of just copying output.

## Why existing tools are not enough

- **Cursor, Cline, Continue, Aider** are coding agents built around editing code. They support many
  models, and some have rules files or memory, but that memory is tied to their own editor and
  workflow, and none of them puts a structured, human-approved project memory at the centre.
- **Chat apps (ChatGPT, Claude)** keep history per provider. Nothing carries over when you switch.
- **Copy and paste** works, but costs about 10 minutes per switch and drops older decisions.

## The one differentiator

**Project memory that survives a model switch.** Decisions, tasks and architecture are stored as
structured, approved records, and Mantle can explain the reasons behind them. They belong to the
project, not to a model or a provider.

## Non-goals (what Mantle will never be)

- An LLM, or a model host.
- A code editor or IDE replacement. Editing happens in your own editor.
- An autonomous agent that changes code or runs commands without human approval.
- A hosted SaaS that holds users' code or API keys on someone else's server (v0.1 is local-only).
- A paid product. Mantle is open source and unpaid; users pay only their own provider costs.

## Main risks

| Risk | Why it matters |
| --- | --- |
| Summaries lose important detail | If the next model misses a key decision, the core promise fails. |
| Existing tools add the same feature | Cursor and others could add cross-model memory. Mantle's edge must be the depth of project memory and the teaching, not only switching. |
| Too much scope for one part-time developer | `vision.md` is very wide; v0.1 must stay small (`docs/mvp-scope.md`). |
| Background LLM calls cost the user money | Handled by decision D10: logged, visible and possible to turn off. |
| The differentiator arrives late | Phase 1 delivers switching with a conversation summary; structured project memory comes in Phase 3 (`docs/phases.md`). |

## Weak points

- **No success number (Q5: "nahi pata").** `docs/prd.md` proposes one based on the 10-minute
  baseline above. It needs your confirmation.
- **Time budget is incomplete (Q4).** You gave 2–4 evenings per branch but not evenings per week.
  The demo date in `docs/phases.md` assumes 3 evenings a week.
- **Differentiator vs Cursor/Cline is a claim, not tested yet.** Nobody has compared them side by
  side. Do one comparison before Phase 3 ends.
- **Only one user so far (you).** It's not yet known whether other developers share this exact
  pain.
- **Open source, but no license chosen yet.**
