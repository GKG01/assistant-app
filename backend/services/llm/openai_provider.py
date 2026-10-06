import asyncio
import logging
from time import perf_counter

from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)

from config.settings import Settings
from services.llm.base import LLMError, LLMProvider, LLMReply

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.openai_api_key
        self._model = settings.openai_model
        self._timeout = settings.openai_timeout_seconds
        self._max_output_tokens = settings.openai_max_output_tokens
        self._client: AsyncOpenAI | None = None
        # SDK debug logging includes request bodies. Keep prompts/headers private.
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("httpx2").setLevel(logging.WARNING)
        logging.getLogger("httpcore2").setLevel(logging.WARNING)

    async def generate(self, message: str, *, system_prompt: str) -> LLMReply:
        started = perf_counter()
        logger.info("AI provider request started")
        try:
            if not self._api_key.get_secret_value().strip():
                raise LLMError("configuration")
            async with asyncio.timeout(self._timeout):
                if self._client is None:
                    self._client = AsyncOpenAI(
                        api_key=self._api_key.get_secret_value(),
                        base_url="https://api.openai.com/v1",
                        timeout=self._timeout,
                        max_retries=0,
                    )
                response = await self._client.responses.create(
                    model=self._model,
                    instructions=system_prompt,
                    input=message,
                    max_output_tokens=self._max_output_tokens,
                    store=False,
                )
            if (
                response.status != "completed"
                or response.error is not None
                or not response.output
                or any(
                    item.type not in {"message", "reasoning"}
                    for item in response.output
                )
            ):
                raise LLMError("invalid_response")
            text = response.output_text
            if not isinstance(text, str) or not text.strip():
                raise LLMError("invalid_response")
            reply = LLMReply(text=text.strip())
        except Exception as exc:
            if isinstance(exc, LLMError):
                error = exc
            elif isinstance(exc, (AuthenticationError, PermissionDeniedError)):
                error = LLMError("authentication")
            elif isinstance(exc, RateLimitError):
                error = LLMError("rate_limit")
            elif isinstance(exc, (APITimeoutError, TimeoutError)):
                error = LLMError("timeout")
            elif isinstance(exc, APIConnectionError):
                error = LLMError("connection")
            elif isinstance(
                exc, (APIResponseValidationError, AttributeError, TypeError, ValueError)
            ):
                error = LLMError("invalid_response")
            else:
                error = LLMError("provider")
            logger.warning(
                "AI provider failure category=%s duration_ms=%.0f",
                error.category,
                (perf_counter() - started) * 1000,
            )
            raise error from None
        logger.info(
            "AI provider request completed duration_ms=%.0f",
            (perf_counter() - started) * 1000,
        )
        return reply

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
