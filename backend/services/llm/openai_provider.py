from typing import Any

from pydantic import SecretStr

from services.llm.base import LLMProvider, LLMReply


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: SecretStr) -> None:
        self._api_key = api_key

    async def generate(self, message: str, tools: list[dict[str, Any]]) -> LLMReply:
        raise NotImplementedError("OpenAI integration is not implemented.")
