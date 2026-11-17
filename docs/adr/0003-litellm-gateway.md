# ADR 0003: LiteLLM behind our own LLM gateway

Status: Accepted

## Context

Switching models without losing context is Mantle's core feature, so the app needs one way to
call many providers (OpenAI, Anthropic, Google, later local models) for chat, streaming,
embeddings and token counting. `vision.md` recommends LiteLLM.

## Decision

Use the **LiteLLM Python SDK** (not the LiteLLM proxy server), imported **only** inside
`modules/llm`. That module is our gateway. It exposes Mantle's own functions (`stream_chat`,
`complete`, `embed`, `count_tokens`) and Mantle's own error types (`RateLimited`,
`ContextTooLong`, `AuthFailed`, `ProviderUnavailable`). It decrypts keys just before each call and
writes a UsageRecord for every call. Tests use a fake provider or LiteLLM's `mock_response`.

## Alternatives considered

- **Each provider's own SDK:** full control, but we'd have to write and maintain every adapter
  ourselves, including their different streaming and error formats.
- **The LiteLLM proxy server:** another process to run and secure, which isn't needed for one
  local user.
- **LangChain chat models:** this would make LangChain part of the core, which is against our
  rules (ADR 0004).

## Consequences

- Adding a provider is usually configuration, not code.
- The rest of Mantle never sees LiteLLM types, so it could be replaced later without touching
  other modules.
- LiteLLM is a large package that releases often, which also makes it a supply-chain target.
  Pin an exact version and review the changelog before upgrading.
- Model data from LiteLLM (context windows, prices) may be out of date, so the user can override it.
