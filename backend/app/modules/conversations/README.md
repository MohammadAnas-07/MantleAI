# conversations

Conversations, streamed replies and model switching. The conversation in Mantle's database is the
source of truth, never a provider's session.

- `service.py`: public interface: create/list conversations, `prepare_reply` + `stream_reply`
  (SSE; retrieves project code first and sends a `warning` event if that fails),
  `preview_handoff`, `switch_model` (never calls the old model).
- `context_builder.py`: builds the request for a target model within its token budget
  (system, pinned items, summary, recent messages, retrieved code as `<source>` blocks within 30%
  of the budget; drops lowest priority first; defangs tags inside data).
- `summary.py`: incremental rolling summary; background job with a per-conversation lock, or at
  switch time with the new model when background summaries are off.
- `suggestions.py`: `suggested_models` for context-limit and rate-limit errors.
- `prompts/`: versioned prompt files (`system_v2.txt` adds the `<source>` and citation rule; `system_v1.txt` and `summary_v1.txt` stay for reference).
- `router.py`: the endpoints in `docs/api-outline.md`.
