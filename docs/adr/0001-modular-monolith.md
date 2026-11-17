# ADR 0001: Modular monolith

Status: Accepted

## Context

Mantle has several clear areas: projects, conversations, LLM gateway, RAG, workflow, teaching and
execution. For now it's built by one developer and used by one local user. `vision.md` says
"start as a modular monolith with clean boundaries; extract services only when scale or ownership
requires it."

## Decision

One FastAPI app, one process, one PostgreSQL database. Each area is a package in
`backend/app/modules/` that owns its own tables and exposes a public `service.py`. Modules call
each other only through those service functions, never through each other's models or tables.
Dependencies point one way: `llm` and `projects` depend on nothing, and there are no cycles.

## Alternatives considered

- **Microservices from the start:** more deployments, network calls and failure modes, and no
  benefit for one user.
- **A plain monolith with no module rules:** fastest at first, but modules would get tangled and
  extracting a service later would be very hard.

## Consequences

- One `uvicorn` command runs everything, which suits a beginner and makes debugging easy.
- Module rules must be enforced by review (and later by an import-linter check in CI).
- Because each module owns its tables, a module can later become its own service with its own
  database if scale ever requires it.
