# llm (LLM gateway)

Every model call in Mantle goes through `service.py`. Other modules never import `litellm` or
name a provider.

- `gateway.py`: `stream_chat`, `complete`, `embed`, `count_tokens`, `test_credential`. Each call
  writes one `usage_records` row (also on error and cancel) and logs metadata only.
- `backend.py`: the interface a backend implements. `litellm_backend.py` is the real backend and
  the only file that imports `litellm`; `fake.py` is `FakeProvider` for tests (scripted replies,
  errors, a call log, no network).
- `errors.py`: `RateLimited`, `QuotaExhausted`, `ContextTooLong`, `AuthFailed`,
  `ProviderUnavailable`, `NoCredential`, `CredentialUnreadable`, `ModelUnavailable`.
  `provider_errors.py` reads the structured parts of a provider's error.
- `crypto.py`: Fernet encryption of provider keys. `key_status.py`: whether the saved keys can be
  decrypted with the current master key (for `/health` and startup).
- `catalog.py`: the default model catalog, added by `python -m app.db.seed`. `providers.py`: the
  supported providers and what each can do.
- `router.py`: providers, credentials, models, model settings and usage endpoints.
