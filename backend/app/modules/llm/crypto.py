"""Fernet encryption for provider API keys.

The master key is MASTER_ENCRYPTION_KEY in backend/.env. Plaintext keys are never stored and
never logged; error messages never contain a key. Decryption happens only inside this module
(rules.md #46).
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

GENERATE_HINT = (
    'Generate one with: python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())" and put it in backend/.env.'
)


class MasterKeyError(RuntimeError):
    """MASTER_ENCRYPTION_KEY is missing or not a valid Fernet key."""


class DecryptionError(RuntimeError):
    """The stored ciphertext can't be decrypted with the current master key."""


def get_fernet(master_key: str | None = None) -> Fernet:
    """Build a Fernet from `master_key`, or from settings when it is None. Fails fast."""
    key = settings.master_encryption_key if master_key is None else master_key
    if not key or not key.strip():
        raise MasterKeyError(f"MASTER_ENCRYPTION_KEY is not set. {GENERATE_HINT}")
    try:
        return Fernet(key.strip().encode())
    except ValueError:
        # Don't chain the original error: its message could echo part of the key.
        raise MasterKeyError(
            "MASTER_ENCRYPTION_KEY is not a valid Fernet key (32 url-safe base64-encoded "
            f"bytes). {GENERATE_HINT}"
        ) from None


def validate_master_key(master_key: str | None = None) -> None:
    """Raise MasterKeyError if the master key is missing or invalid."""
    get_fernet(master_key)


def encrypt_secret(plaintext: str, master_key: str | None = None) -> bytes:
    if not plaintext:
        raise ValueError("Cannot encrypt an empty secret.")
    return get_fernet(master_key).encrypt(plaintext.encode())


def decrypt_secret(ciphertext: bytes, master_key: str | None = None) -> str:
    try:
        return get_fernet(master_key).decrypt(ciphertext).decode()
    except InvalidToken:
        raise DecryptionError(
            "Stored key can't be decrypted. Was MASTER_ENCRYPTION_KEY changed?"
        ) from None


def key_hint(plaintext: str) -> str:
    """The last 4 characters of a key, for display. Empty for keys shorter than 8 characters,
    so a hint never reveals most of a key."""
    return plaintext[-4:] if len(plaintext) >= 8 else ""
