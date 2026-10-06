from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from agent.schemas import ToolCall


class LLMReply(BaseModel):
    text: str | None = None
    tool_call: ToolCall | None = None


FailureCategory = Literal[
    "configuration",
    "authentication",
    "rate_limit",
    "timeout",
    "connection",
    "invalid_response",
    "provider",
]


class LLMError(Exception):
    """Provider-neutral failure; never carry SDK messages, headers or bodies."""

    def __init__(self, category: FailureCategory) -> None:
        self.category = category
        super().__init__(category)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, message: str, *, system_prompt: str) -> LLMReply:
        """Generate text for one independent request. No tools are available."""
        raise NotImplementedError

    async def close(self) -> None:
        """Release provider resources when the owning application shuts down."""
