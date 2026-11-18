# llm (LLM gateway)

Every model call in Mantle goes through `service.py`. Other modules never import `litellm` or
name a provider.

- `gateway.py`: `stream_chat`, `complete`, `embed`, `count_tokens`, `test_credential`. Each call
  writes one `usage_records` row (also on error and cancel) and logs metadata only.
- `litellm_backend.py`: the real backend, and the only file that imports `litellm`.
- `fake.py`: `FakeProvider` for tests: scripted replies, errors, a call log, no network.
- `errors.py`: `RateLimited`, `ContextTooLong`, `AuthFailed`, `ProviderUnavailable`,
  `NoCredential`, `ModelUnavailable`.
- `crypto.py`: Fernet encryption of provider keys.
- `catalog.py`: the default model catalog, added by `python -m app.db.seed`.
- `router.py`: providers, credentials, models, model settings and usage endpoints.
