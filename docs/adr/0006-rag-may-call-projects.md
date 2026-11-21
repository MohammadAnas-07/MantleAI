# ADR 0006: rag may call projects, and a test checks module directions

Status: Accepted (2026-11-18, `feat/project-indexing-rag`)

## Context

The project's folder (`projects.root_path`) is owned by the projects module, but only the rag
module may read project files (rule 10), and indexing needs the folder. The architecture table
said rag may call only llm. The project list and detail responses should also show whether the
project is indexed (`last_indexed_at`, `needs_reindex`), which only rag knows, while projects may
call no module.

## Decision

- rag may call projects (through `projects/service.py` only): to check that a project exists,
  read its `root_path`, and store a folder that rag has validated (`set_root_path`). projects
  still calls no module, so there is no cycle.
- The routes that show a project with its index status (`GET /projects`, `POST /projects`,
  `GET /projects/{id}`) move to `app/api/projects.py`, a thin layer above the modules that may
  use any module's service. The list asks rag for the status of all projects at once
  (`index_status_many`), so it runs a fixed number of queries, whatever the project count.
- `tests/test_module_boundaries.py` parses every file under `app/modules` and fails when a module
  imports a module the table doesn't allow, or imports anything but its `service.py`. It also
  checks that the table has no cycle.

The allowed directions are now:

| Module | May call |
| --- | --- |
| projects, llm, execution | none |
| rag | llm, projects |
| conversations | projects, rag, llm |
| workflow | projects, rag, llm |
| teaching | projects, conversations, rag, llm |

## Alternatives considered

- Move `root_path` into a rag-owned table. Keeps the old table, but splits one project's data
  over two modules and needs a data migration for a column that already exists.
- Let the projects router call rag. Creates a projects ↔ rag cycle.
- Have every caller pass the folder to rag. Each caller would repeat the lookup and could pass
  an unvalidated path.

## Consequences

- A new dependency direction must be added to the table in `docs/architecture.md`, to this list
  and to `ALLOWED` in the test, in the same PR.
- `app/api` is the place for future endpoints that combine modules.
