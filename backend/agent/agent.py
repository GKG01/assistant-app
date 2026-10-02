from agent.schemas import AgentRequest, AgentResponse
from agent.tool_registry import ToolRegistry
from permissions.manager import PermissionManager
from services.llm.base import LLMProvider


class Agent:
    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        permissions: PermissionManager,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._permissions = permissions

    async def respond(self, request: AgentRequest) -> AgentResponse:
        # Future: provider proposes a ToolCall; only permissions.dispatch executes it.
        raise NotImplementedError("Agent orchestration is not implemented.")
