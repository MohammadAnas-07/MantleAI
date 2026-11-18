"""Password hashing and session tokens."""

import hashlib
import hmac
import os
import time

TOKEN_LIFETIME_SECONDS = 3600
HASH_ITERATIONS = 200_000


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """PBKDF2-SHA256 with a random salt. Returns (salt, digest)."""
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, HASH_ITERATIONS)
    return salt, digest


def verify_password(password: str, salt: bytes, expected: bytes) -> bool:
    _, digest = hash_password(password, salt)
    return hmac.compare_digest(digest, expected)


def create_session_token(user_id: int, signing_secret: bytes) -> str:
    """A signed token: user id, expiry time and an HMAC signature."""
    expires = int(time.time()) + TOKEN_LIFETIME_SECONDS
    payload = f"{user_id}.{expires}"
    signature = hmac.new(signing_secret, payload.encode(), "sha256").hexdigest()
    return f"{payload}.{signature}"


def verify_session_token(token: str, signing_secret: bytes) -> int | None:
    """The user id of a valid, unexpired token, else None."""
    user_id, expires, signature = token.split(".")
    payload = f"{user_id}.{expires}"
    good = hmac.new(signing_secret, payload.encode(), "sha256").hexdigest()
    if not hmac.compare_digest(good, signature) or int(expires) < time.time():
        return None
    return int(user_id)
