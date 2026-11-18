"""The LLM gateway: every model call in Mantle goes through here (rule 33).

For each call it resolves the model from the catalog, finds the user's key for the model's
provider, decrypts it (only here, rule 46), calls the backend, writes one `usage_records` row
(rule 35, no exceptions) and logs metadata only (rule 53/54).

The caller owns the database transaction: the gateway flushes the usage row, the caller commits.
Always consume `stream_chat` with `contextlib.aclosing(...)`, so a cancelled stream still writes
its usage row before the session goes away.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from decimal import Decimal

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.modules.llm.backend import Backend, ChatMessages, EmbedInputType, TextDelta, UsageInfo
from app.modules.llm.crypto import decrypt_secret
from app.modules.llm.errors import LLMError, ModelUnavailable, NoCredential
from app.modules.llm.models import (
    ModelConfig,
    ModelKind,
    ProviderCredential,
    UsagePurpose,
    UsageStatus,
    UsageTrigger,
)
from app.modules.llm.repository import (
    ModelConfigRepository,
    ProviderCredentialRepository,
    UsageRecordRepository,
)

logger = logging.getLogger(__name__)

_MTOK = Decimal(1_000_000)


@dataclass(frozen=True)
class UsageLinks:
    """Optional links stored on the usage row."""

    project_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    agent_run_id: uuid.UUID | None = None


@dataclass(frozen=True)
class ChatDelta:
    text: str


@dataclass(frozen=True)
class ChatDone:
    text: str
    model_id: uuid.UUID
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None
    latency_ms: int
    usage_record_id: uuid.UUID


ChatEvent = ChatDelta | ChatDone


def _cost(model: ModelConfig, input_tokens: int, output_tokens: int) -> Decimal | None:
    if model.input_cost_per_mtok is None or model.output_cost_per_mtok is None:
        return None
    return (
        Decimal(input_tokens) * model.input_cost_per_mtok
        + Decimal(output_tokens) * model.output_cost_per_mtok
    ) / _MTOK


class Gateway:
    def __init__(self, backend: Backend) -> None:
        self.backend = backend

    # ---- lookups -------------------------------------------------------------------------

    async def get_model(
        self, session: AsyncSession, model_id: uuid.UUID, kind: ModelKind | None = None
    ) -> ModelConfig:
        model = await ModelConfigRepository(session).get(model_id)
        if model is None or not model.enabled:
            raise ModelUnavailable("This model doesn't exist or is disabled.")
        if kind is not None and model.kind != kind:
            raise ModelUnavailable(f"This model can't be used for {kind.value}.")
        return model

    async def _api_key(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        model: ModelConfig,
        credential: ProviderCredential | None,
    ) -> str:
        if credential is None:
            credential = await ProviderCredentialRepository(session, user_id).latest_for_provider(
                model.provider
            )
        if credential is None:
            raise NoCredential(
                f"Add an API key for {model.provider} to use this model.",
                details={"provider": model.provider},
            )
        return decrypt_secret(credential.encrypted_key)

    def count_tokens(self, model: ModelConfig, messages: ChatMessages) -> int:
        """Estimated prompt tokens of `messages` for `model` (no network)."""
        return self.backend.count_tokens(model.litellm_model, messages)

    # ---- calls ---------------------------------------------------------------------------

    async def stream_chat(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        model_id: uuid.UUID,
        messages: ChatMessages,
        *,
        purpose: UsagePurpose,
        trigger: UsageTrigger,
        max_tokens: int | None = None,
        links: UsageLinks | None = None,
        credential: ProviderCredential | None = None,
    ) -> AsyncIterator[ChatEvent]:
        """Stream a chat reply: ChatDelta events, then one ChatDone.

        Raises typed LLMErrors. A usage row is written for success, error and cancellation.
        """
        model = await self.get_model(session, model_id, ModelKind.CHAT)
        api_key = await self._api_key(session, user_id, model, credential)
        if max_tokens is None:
            max_tokens = model.max_output_tokens

        started = time.monotonic()
        parts: list[str] = []
        usage: UsageInfo | None = None
        status = UsageStatus.ERROR
        error_code: str | None = "internal_error"
        record_id: uuid.UUID | None = None
        try:
            stream = self.backend.stream_chat(
                model.litellm_model, messages, api_key=api_key, max_tokens=max_tokens
            )
            async with aclosing(stream):  # type: ignore[type-var]
                async for item in stream:
                    if isinstance(item, TextDelta):
                        parts.append(item.text)
                        yield ChatDelta(item.text)
                    else:
                        usage = item
            status, error_code = UsageStatus.SUCCESS, None
        except LLMError as exc:
            error_code = exc.code
            raise
        except (GeneratorExit, asyncio.CancelledError):
            # The caller stopped reading (client disconnect) or the task was cancelled.
            status, error_code = UsageStatus.CANCELLED, None
            raise
        finally:
            text = "".join(parts)
            if usage is None:
                usage = UsageInfo(
                    self.count_tokens(model, messages),
                    self.count_tokens(model, [{"role": "assistant", "content": text}])
                    if text
                    else 0,
                )
            # Shielded: under Starlette/anyio a cancelled request cancels every later await, and
            # the usage row must still be written (rule 35).
            with anyio.CancelScope(shield=True):
                record_id = await self._record(
                    session,
                    user_id,
                    model,
                    purpose=purpose,
                    trigger=trigger,
                    usage=usage,
                    started=started,
                    status=status,
                    error_code=error_code,
                    links=links,
                )
        yield ChatDone(
            text=text,
            model_id=model.id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=_cost(model, usage.input_tokens, usage.output_tokens),
            latency_ms=int((time.monotonic() - started) * 1000),
            usage_record_id=record_id,
        )

    async def complete(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        model_id: uuid.UUID,
        messages: ChatMessages,
        *,
        purpose: UsagePurpose,
        trigger: UsageTrigger,
        max_tokens: int | None = None,
        links: UsageLinks | None = None,
        credential: ProviderCredential | None = None,
    ) -> ChatDone:
        """A whole (non-streamed) reply. Same usage and error rules as `stream_chat`."""
        done: ChatDone | None = None
        stream = self.stream_chat(
            session,
            user_id,
            model_id,
            messages,
            purpose=purpose,
            trigger=trigger,
            max_tokens=max_tokens,
            links=links,
            credential=credential,
        )
        async with aclosing(stream):
            async for event in stream:
                if isinstance(event, ChatDone):
                    done = event
        assert done is not None
        return done

    async def embed(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        model_id: uuid.UUID,
        texts: list[str],
        *,
        trigger: UsageTrigger,
        links: UsageLinks | None = None,
        credential: ProviderCredential | None = None,
        purpose: UsagePurpose = UsagePurpose.EMBEDDING,
        input_type: EmbedInputType | None = None,
    ) -> list[list[float]]:
        """Embed `texts` with an embedding model. Vectors have the model's catalog dimension.

        `input_type` is "document" for stored text and "query" for a search query. One usage
        row is written for success and for error.
        """
        model = await self.get_model(session, model_id, ModelKind.EMBEDDING)
        api_key = await self._api_key(session, user_id, model, credential)
        started = time.monotonic()
        try:
            result = await self.backend.embed(
                model.litellm_model,
                texts,
                api_key=api_key,
                dimensions=model.embedding_dimensions,
                input_type=input_type,
            )
        except LLMError as exc:
            await self._record(
                session,
                user_id,
                model,
                purpose=purpose,
                trigger=trigger,
                usage=UsageInfo(0, 0),
                started=started,
                status=UsageStatus.ERROR,
                error_code=exc.code,
                links=links,
            )
            raise
        await self._record(
            session,
            user_id,
            model,
            purpose=purpose,
            trigger=trigger,
            usage=UsageInfo(result.input_tokens, 0),
            started=started,
            status=UsageStatus.SUCCESS,
            error_code=None,
            links=links,
        )
        return result.vectors

    async def test_credential(
        self, session: AsyncSession, user_id: uuid.UUID, credential_id: uuid.UUID
    ) -> tuple[bool, str | None, uuid.UUID]:
        """Make the smallest possible call with this exact key. Returns (ok, error_code, model)."""
        credential = await ProviderCredentialRepository(session, user_id).get(credential_id)
        if credential is None:
            raise NotFound("Credential not found.")
        models = await ModelConfigRepository(session).list(
            provider=credential.provider, enabled=True, limit=100
        )
        if not models:
            raise ModelUnavailable(
                f"No enabled model for {credential.provider} to test the key with."
            )
        chat = [m for m in models if m.kind == ModelKind.CHAT]
        model = chat[0] if chat else models[0]
        trigger = UsageTrigger.USER
        try:
            if model.kind == ModelKind.CHAT:
                await self.complete(
                    session,
                    user_id,
                    model.id,
                    [{"role": "user", "content": "Reply with OK."}],
                    purpose=UsagePurpose.KEY_TEST,
                    trigger=trigger,
                    max_tokens=1,
                    credential=credential,
                )
            else:
                await self.embed(
                    session,
                    user_id,
                    model.id,
                    ["ok"],
                    trigger=trigger,
                    credential=credential,
                    purpose=UsagePurpose.KEY_TEST,
                )
            return True, None, model.id
        except LLMError as exc:
            return False, exc.code, model.id

    # ---- usage ---------------------------------------------------------------------------

    async def _record(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        model: ModelConfig,
        *,
        purpose: UsagePurpose,
        trigger: UsageTrigger,
        usage: UsageInfo,
        started: float,
        status: UsageStatus,
        error_code: str | None,
        links: UsageLinks | None,
    ) -> uuid.UUID:
        latency_ms = int((time.monotonic() - started) * 1000)
        links = links or UsageLinks()
        row = await UsageRecordRepository(session, user_id).add(
            model_id=model.id,
            purpose=purpose,
            trigger=trigger,
            project_id=links.project_id,
            conversation_id=links.conversation_id,
            message_id=links.message_id,
            agent_run_id=links.agent_run_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=_cost(model, usage.input_tokens, usage.output_tokens),
            latency_ms=latency_ms,
            status=status,
            error_code=error_code,
        )
        # Metadata only: never prompts, replies or keys (rule 53).
        logger.info(
            "llm call model=%s purpose=%s trigger=%s status=%s input_tokens=%d "
            "output_tokens=%d latency_ms=%d",
            model.litellm_model,
            purpose.value,
            trigger.value,
            status.value,
            usage.input_tokens,
            usage.output_tokens,
            latency_ms,
        )
        return row.id
