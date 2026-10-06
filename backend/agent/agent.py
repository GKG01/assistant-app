from agent.schemas import AgentRequest, AgentResponse
from agent.prompts import SYSTEM_PROMPT
from services.llm.base import LLMError, LLMProvider


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
    ) -> None:
        self._provider = provider

    async def respond(self, request: AgentRequest) -> AgentResponse:
        try:
            reply = await self._provider.generate(
                request.message, system_prompt=SYSTEM_PROMPT
            )
            if reply.tool_call is not None or not reply.text or not reply.text.strip():
                raise LLMError("invalid_response")
            return AgentResponse(message=reply.text.strip())
        except LLMError:
            raise
        except Exception:
            # A replacement provider must not leak its internals through FastAPI.
            raise LLMError("provider") from None
