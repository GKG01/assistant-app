from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from agent.schemas import ToolCall


class LLMReply(BaseModel):
    text: str | None = None
    tool_call: ToolCall | None = None


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, message: str, tools: list[dict[str, Any]]) -> LLMReply:
        """Return text or a proposed call, never execute a tool."""
        raise NotImplementedError
