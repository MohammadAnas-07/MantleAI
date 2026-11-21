# conversations

Conversations, streamed replies and model switching. The conversation in Mantle's database is the
source of truth, never a provider's session.

- `service.py`: public interface: create/list conversations, `prepare_reply` + `stream_reply`
  (SSE; retrieves project code first and sends a `warning` event if that fails),
  `preview_handoff`, `switch_model` (never calls the old model).
- `context_builder.py`: builds the request for a target model within its token budget (system,
  pinned items, project profile, summary, recent messages, retrieved code as `<source>` blocks
  within 30% of the budget). It drops the lowest priority first and defangs tags inside data.
- `summary.py`: incremental rolling summary; background job with a per-conversation lock, or at
  switch time with the new model when background summaries are off.
- `prompts/`: versioned prompt files. In use: `system_v3.txt` (it adds the project profile) and
  `summary_v1.txt`. `system_v2.txt` added the `<source>` and citation rule; it and
  `system_v1.txt` stay for reference.
- Suggested models for limit errors come from `llm`'s `suggest_models`.
- `router.py`: the endpoints in `docs/api-outline.md`.
