"""Whether the saved provider keys can be decrypted with the current MASTER_ENCRYPTION_KEY.

Used by /health and at startup. It reports a status word only: no key, ciphertext or provider
text ever leaves this file. It never changes or deletes a saved key.
"""

from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import UserRepository
from app.modules.llm.crypto import can_decrypt
from app.modules.llm.repository import ProviderCredentialRepository


class KeyStatus(StrEnum):
    NONE = "none"  # no key saved yet
    OK = "ok"  # the key used for every provider can be decrypted
    UNREADABLE = "unreadable"  # at least one can't: the master key changed


async def unreadable_providers(session: AsyncSession) -> list[str]:
    """Providers whose newest saved key (the one calls use) can't be decrypted, for the
    default local user (v0.1 has one user). None of the key material is kept."""
    user = await UserRepository(session).get_default()
    if user is None:
        return []
    repo = ProviderCredentialRepository(session, user.id)
    out = []
    for provider in sorted(await repo.providers_with_keys()):
        credential = await repo.latest_for_provider(provider)
        if credential is not None and not can_decrypt(credential.encrypted_key):
            out.append(provider)
    return out


async def key_status(session: AsyncSession) -> KeyStatus:
    user = await UserRepository(session).get_default()
    if user is None:
        return KeyStatus.NONE
    if not await ProviderCredentialRepository(session, user.id).providers_with_keys():
        return KeyStatus.NONE
    return KeyStatus.UNREADABLE if await unreadable_providers(session) else KeyStatus.OK
