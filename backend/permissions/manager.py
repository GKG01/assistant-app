from pydantic import ValidationError

from agent.schemas import PendingAction, ToolCall, ToolResult
from agent.tool_registry import ToolRegistry
from permissions.policies import Decision, classify


class PermissionManager:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def dispatch(self, call: ToolCall) -> ToolResult | PendingAction:
        # Risk comes from trusted registration, never from model-supplied arguments.
        tool = self._registry.get(call.tool)
        decision = classify(tool.risk)
        if decision == Decision.DENY:
            return ToolResult(tool=tool.name, status="denied",
                              message="Destructive tools are disabled in V1.")
        try:
            arguments = tool.input_schema.model_validate(call.arguments)
        except ValidationError:
            return ToolResult(tool=tool.name, status="error",
                              message="Invalid tool arguments.")
        if decision == Decision.CONFIRM:
            # No confirm endpoint exists yet; pending actions cannot execute.
            return PendingAction(tool=tool.name, arguments=arguments.model_dump(mode="json"),
                                 risk=tool.risk)
        try:
            return ToolResult(tool=tool.name, status="completed", data=tool.execute(arguments))
        except ValueError as exc:
            return ToolResult(tool=tool.name, status="error", message=str(exc))
