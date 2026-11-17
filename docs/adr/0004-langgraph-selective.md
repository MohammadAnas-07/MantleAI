# ADR 0004: Use LangGraph selectively

Status: Accepted (see Open question 7 in `docs/architecture.md`)

## Context

v0.1 has two agents, Planner and Reviewer, working inside workflow stages that need human
approval. `vision.md` suggests LangGraph for stateful agent workflows, but says Mantle must own its
core architecture and must not create agents "for the sake of calling something an AI agent."
Our rule: no LangChain in core code.

## Decision

- LangGraph is used **only inside `modules/workflow`**, to run the agent steps of one stage
  (Planner drafts → Reviewer critiques → Planner revises once → stop).
- Graph nodes are plain Python functions that call **our** LLM gateway. We never use LangChain
  chat models, prompts, retrievers or memory classes.
- **Our tables** (StageState, AgentRun) are the source of truth for stage status and approval.
  Human approval happens through our API, between graph runs. A LangGraph checkpointer isn't
  needed in v0.1.
- Chat, model switching, RAG and teaching are plain Python with no LangGraph.

## Alternatives considered

- **No framework (a hand-written state machine):** enough for two agents, and we may still choose
  it. LangGraph pays off once there are more agents, branches and retries.
- **LangChain agents:** this would put LangChain at the centre of the app, which goes against the
  vision and our rule.
- **Other agent frameworks (CrewAI, AutoGen):** more autonomous by design, which is the opposite of
  "human control over autonomous agents."

## Consequences

- The use of LangGraph is contained, so it can be removed by rewriting one module.
- `langgraph` installs `langchain-core` as a dependency. Our code must never import it
  (enforced by review and later a lint rule).
- Adding agents later means adding nodes to the graph, not changing other modules.
