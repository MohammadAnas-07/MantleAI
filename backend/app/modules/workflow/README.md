# workflow

Workflow stages, the gap finder, and Planner and Reviewer runs. A plain Python state machine with
every state saved in PostgreSQL; no LangGraph in v0.1 (ADR 0004). May call projects, rag and llm.
The app uses only `service.py`.

- `stages.yaml`, `stages.py`: the stage definitions, checked when the API starts.
- `state.py`: current stage, checklist, gates and transitions. Each change checks a version
  number and writes one append-only `WorkflowEvent`. No LLM call.
- `gap_finder.py`: one user-requested call that lists missing steps, risks, technical debt and
  scalability concerns. It proposes nothing to save.
- `runs.py`, `steps.py`, `run_setup.py`: agent runs (Planner, then Reviewer, then the user's
  decision), one model call per step with at most one retry, the cost estimate and guard, and one
  active run per project.
- `context.py`: what the agents see, each piece of project data inside its own defanged tag.
- `outputs.py`: parses and validates model output. It is stored as a draft and never executed.
- `approval.py`: the only path from agent output to project memory: the user saves all or some
  drafts, or rejects the run.
- `models.py`, `repository.py`, `views.py`, `router.py`, `schemas.py`, `prompts/`: tables
  (migration `0008`), queries, API views, the endpoints in `docs/api-outline.md`, and the
  versioned prompt files.
