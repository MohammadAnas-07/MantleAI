"""Provider-key encryption. Uses only generated test keys."""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.main import app, lifespan
from app.modules.llm.crypto import (
    DecryptionError,
    MasterKeyError,
    decrypt_secret,
    encrypt_secret,
    key_hint,
    validate_master_key,
)
from app.modules.llm.repository import ProviderCredentialRepository
from tests.graph import FAKE_API_KEY, make_user

SECRET = "sk-test-0000000000000000abcd"


def test_round_trip() -> None:
    ciphertext = encrypt_secret(SECRET)
    assert decrypt_secret(ciphertext) == SECRET


def test_ciphertext_is_not_the_plaintext() -> None:
    ciphertext = encrypt_secret(SECRET)
    assert SECRET.encode() not in ciphertext
    assert b"abcd" not in ciphertext


def test_wrong_key_fails() -> None:
    ciphertext = encrypt_secret(SECRET)
    other_key = Fernet.generate_key().decode()
    with pytest.raises(DecryptionError):
        decrypt_secret(ciphertext, master_key=other_key)


@pytest.mark.parametrize("missing", ["", "   "])
def test_missing_master_key_fails_fast(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    monkeypatch.setattr(settings, "master_encryption_key", missing)
    with pytest.raises(MasterKeyError, match="MASTER_ENCRYPTION_KEY is not set"):
        validate_master_key()
    with pytest.raises(MasterKeyError):
        encrypt_secret(SECRET)


def test_invalid_master_key_fails_without_echoing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_key = "not-a-fernet-key-but-secret-looking"
    monkeypatch.setattr(settings, "master_encryption_key", bad_key)
    with pytest.raises(MasterKeyError, match="not a valid Fernet key") as info:
        validate_master_key()
    assert bad_key not in str(info.value)
    assert info.value.__cause__ is None


async def test_app_refuses_to_start_without_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "master_encryption_key", "")
    with pytest.raises(MasterKeyError):
        async with lifespan(app):
            pass


def test_key_hint_shows_only_last_four() -> None:
    assert key_hint(SECRET) == "abcd"
    assert key_hint("short") == ""


@pytest.mark.db
async def test_stored_credential_is_encrypted(session: AsyncSession) -> None:
    user_id = await make_user(session, "Dana")
    repo = ProviderCredentialRepository(session, user_id)
    credential = await repo.add_key(provider="openai", api_key=FAKE_API_KEY)

    raw = await session.scalar(
        text("SELECT encrypted_key FROM provider_credentials WHERE id = :id"),
        {"id": credential.id},
    )
    assert raw is not None
    assert FAKE_API_KEY.encode() not in bytes(raw)
    assert decrypt_secret(bytes(raw)) == FAKE_API_KEY
    assert credential.key_hint == FAKE_API_KEY[-4:]

    with pytest.raises(TypeError):
        await repo.add(provider="openai", encrypted_key=b"x", key_hint="")
