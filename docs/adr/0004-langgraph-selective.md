# ADR 0004: Use LangGraph selectively

Status: Accepted (decision D7 in `docs/architecture.md`, 2026-11-17). Amended 2026-11-19 in
`feat/workflow-and-agents`: v0.1 uses no LangGraph.

## Context

v0.1 has two agents, Planner and Reviewer, working inside workflow stages that need human
approval. `vision.md` suggests LangGraph for stateful agent workflows, but says Mantle must own its
core architecture and must not create agents "for the sake of calling something an AI agent."
Our rule: we never import `langchain*`; only `langgraph`.

The original note said: if Planner and Reviewer can be built as plain Python (a small state
machine over our own tables), skip LangGraph, and decide this at the start of
`feat/workflow-and-agents`.

## Decision (2026-11-19)

No LangGraph in v0.1. The flow is short and fixed: Planner, then Reviewer, then a pause for
the user's approval. There is no revision loop: the Planner does not revise its plan after the
review; the user decides.

- `app/modules/workflow/runs.py` is a plain Python state machine:
  `queued -> running -> waiting_for_approval -> approved | rejected` for a plan run,
  `queued -> running -> completed` for a review-only run, and `failed` or `cancelled` from any
  active state.
- Every state and every step (agent, prompt version, model, tokens, cost, latency, output,
  error) is saved in PostgreSQL (`agent_runs`, `agent_run_steps`). The run commits after each
  step, so polling shows progress and a restart loses at most the step in flight; startup marks
  queued and running runs failed ("interrupted").
- Steps call our LLM gateway. Agents have no tools. Their output is a validated draft; only
  the user's approval writes project memory.
- `langgraph` is not a dependency, so `langchain-core` isn't installed either.

This also removes the need for a second database driver and a checkpointer: our tables already
hold the state between the run and the human decision.

## When to revisit

Add LangGraph (still only inside `modules/workflow`, still never `langchain*`) when one of these
arrives and the plain loop starts to get messy:

- Loops: an agent that revises its own output after review, or retries with a critic, more
  than once.
- Parallel agents: several agents working on one stage at the same time and merging results.
- Long-running, branching flows: flows that pause for people in more than one place, branch
  on results, or must resume mid-step after a restart.

## Alternatives considered

- LangGraph now: pays off with more agents, branches and retries. For two fixed steps it adds a
  dependency (and `langchain-core`), a checkpointer or a second source of truth, and more to learn
  for no gain.
- LangChain agents: this would put LangChain at the centre of the app, which goes against the
  vision and our rule.
- Other agent frameworks (CrewAI, AutoGen): more autonomous by design, which is the opposite of
  "human control over autonomous agents."

## Consequences

- The agent flow is one file of plain Python (`runs.py`) that any contributor can read and test with
  FakeProvider.
- Adding a step means adding a call in `runs.py` and a prompt file; adding loops or parallel
  agents is the point where we reconsider this ADR.
- The rule "only `langgraph`, only in `modules/workflow`, never `langchain*`" stays in force for
  when LangGraph is added.
