# conversations

Conversations, streamed replies and model switching. The conversation in Mantle's database is the
source of truth, never a provider's session.

- `service.py`: public interface: create/list conversations, `prepare_reply` + `stream_reply`
  (SSE), `preview_handoff`, `switch_model` (never calls the old model).
- `context_builder.py`: builds the request for a target model within its token budget
  (system, pinned items, summary, recent messages, retrieved context; drops lowest priority first).
- `summary.py`: incremental rolling summary; background job with a per-conversation lock, or at
  switch time with the new model when background summaries are off.
- `suggestions.py`: `suggested_models` for context-limit and rate-limit errors.
- `prompts/`: versioned prompt files (`system_v1.txt`, `summary_v1.txt`).
- `router.py`: the endpoints in `docs/api-outline.md`.
