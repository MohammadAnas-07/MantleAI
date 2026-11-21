# projects

Projects and project memory: requirements, decisions and tasks. Calls no other module. Other
modules use only `service.py`; nothing here calls an LLM.

- `service.py`: the public interface (get, create, list, update and delete a project, store a
  folder that rag has checked, pinned memory, memory references).
- `memory_service.py`: memory rules. Memory is written only by the user, or from agent drafts the
  user approved. Another user's or project's item is a 404. Edits are last-write-wins.
- `pinned.py`: which memory items go into a prompt as `<pinned_items>`, in a fixed order, and their
  text. No I/O, no LLM.
- `models.py`, `repository.py`: `Project`, `MemoryItem`, `MemoryDependency`; every query filters
  by `user_id`.
- `router.py`, `schemas.py`: the memory endpoints in `docs/api-outline.md`. The project list,
  create and detail routes are in `app/api/projects.py` (ADR 0006).
