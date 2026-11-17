# ADR 0005: Local-first, single user

Status: Accepted

## Context

The first users are individual developers who want to try Mantle on their own projects with their
own API keys. Building accounts, auth, tenancy and hosting now would delay the core features
(model switching, RAG, workflow). `vision.md` wants a path from "single-user local development
tool" to a multi-user platform.

## Decision

v0.1 runs entirely on the user's machine for one user:

- The backend runs natively and binds to `127.0.0.1`. PostgreSQL runs in Docker on localhost.
- There are no accounts and no login. No `users` table yet.
- Users bring their own provider keys, stored encrypted with a master key from `backend/.env`.
- Projects are local folders that the backend reads directly.
- Protection against websites calling the local API: strict CORS, Host-header checks, JSON-only
  writes (see `docs/security.md`).

## Alternatives considered

- **A hosted multi-user SaaS from day one:** needs auth, tenancy, billing and hosting first, and
  the user's code would leave their machine.
- **A desktop app (Electron or Tauri):** nicer to install, but adds a second build system before
  the product is proven.
- **No database (files only):** simpler, but no vector search and a hard migration later.

## Consequences

- Simple setup, no hosting cost, and code stays local (except what is sent to the chosen LLM
  provider).
- Mantle **must not** be exposed on a network until `feat/authentication` is done.
- Going multi-user later needs a migration that adds `users`, ownership columns and per-user key
  storage. Module boundaries (ADR 0001) keep that change contained.
