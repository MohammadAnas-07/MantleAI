"""Model suggestions for ContextTooLong, RateLimited and QuotaExhausted errors.

Mantle never switches models on its own (assumption 6): it only lists models the user could
switch to. Only enabled chat models whose provider the user has a key for are suggested.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.llm.service import ModelInfo, list_chat_models, providers_with_keys


async def suggest_models(
    session: AsyncSession, user_id: uuid.UUID, current: ModelInfo, reason: str
) -> list[dict[str, Any]]:
    """`reason` is `context_too_long` (bigger window), or `rate_limited` or `quota_exhausted`
    (another provider)."""
    with_keys = await providers_with_keys(session, user_id)
    candidates = [
        m for m in await list_chat_models(session) if m.id != current.id and m.provider in with_keys
    ]
    if reason == "context_too_long":
        picked = [m for m in candidates if m.context_window > current.context_window]
    else:
        picked = [m for m in candidates if m.provider != current.provider]
    picked.sort(key=lambda m: (-m.context_window, m.display_name))
    return [
        {
            "model_id": str(m.id),
            "display_name": m.display_name,
            "provider": m.provider,
            "context_window": m.context_window,
        }
        for m in picked
    ]
