from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.schemas import ToolCall


class LLMToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=256, pattern=r"^\S+$")
    name: str = Field(min_length=1, max_length=128, pattern=r"^\S+$")
    arguments: str


class LLMToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class LLMToolResultMessage(BaseModel):
    call_id: str
    output: str


class LLMReply(BaseModel):
    text: str | None = None
    tool_call: ToolCall | None = None  # Legacy text-provider placeholder.
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    # Opaque, request-local provider continuation; never interpreted by the agent.
    continuation: str | None = Field(default=None, repr=False)


class LLMToolTurn(BaseModel):
    reply: LLMReply
    results: list[LLMToolResultMessage]


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

    async def generate_with_tools(
        self,
        message: str,
        *,
        system_prompt: str,
        tools: list[LLMToolDefinition],
        turns: list[LLMToolTurn],
    ) -> LLMReply:
        # Existing text-only providers remain usable; they cannot request tools.
        if turns:
            raise LLMError("invalid_response")
        reply = await self.generate(message, system_prompt=system_prompt)
        if reply.tool_calls:
            raise LLMError("invalid_response")
        return reply

    async def close(self) -> None:
        """Release provider resources when the owning application shuts down."""
