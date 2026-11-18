import logging

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import SecretMaskingFilter, mask_secrets
from app.modules.llm.catalog import DEFAULT_MODELS, seed_default_models
from app.modules.llm.repository import ModelConfigRepository


@pytest.mark.db
async def test_seed_models_is_idempotent_and_keeps_user_changes(session: AsyncSession) -> None:
    assert await seed_default_models(session) == len(DEFAULT_MODELS)
    repo = ModelConfigRepository(session)
    gpt = await repo.get_by_litellm_model("openai/gpt-5.6")
    assert gpt is not None
    await repo.update(gpt.id, context_window=1234)

    assert await seed_default_models(session) == 0
    gpt = await repo.get_by_litellm_model("openai/gpt-5.6")
    assert gpt is not None and gpt.context_window == 1234


@pytest.mark.parametrize(
    "secret",
    [
        "sk-proj-abcdefghijklmnop1234",
        "sk-ant-api03-abcdefghijklmnop",
        "AIzaSyAbcdefghijklmnopqrstuvwx",
        "pa-abcdefghijklmnopqrstuvwxyz12",
    ],
)
def test_mask_secrets(secret: str) -> None:
    assert secret not in mask_secrets(f"calling with {secret} now")


def test_mask_authorization_header() -> None:
    masked = mask_secrets("Authorization: Bearer abc.def.ghi and api_key=xyz123")
    assert "abc.def.ghi" not in masked and "xyz123" not in masked
    assert "Authorization" in masked


def test_filter_masks_log_records() -> None:
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "key %s", ("sk-abcdefghijk123",), None
    )
    SecretMaskingFilter().filter(record)
    assert "sk-abcdefghijk123" not in record.getMessage()
