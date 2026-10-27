from pydantic import ValidationError

from agent.schemas import PendingAction, ToolCall, ToolResult
from agent.tool_registry import ToolRegistry
from permissions.policies import Decision, RiskLevel, classify


class PermissionManager:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def dispatch(
        self, call: ToolCall, *, user_initiated: bool = False, read_only: bool = False
    ) -> ToolResult | PendingAction:
        # Risk comes from trusted registration, never from model-supplied arguments.
        tool = self._registry.get(call.tool)
        if read_only and tool.risk != RiskLevel.READ:
            return ToolResult(
                tool=tool.name, status="denied", message="Only READ tools are allowed."
            )
        decision = classify(tool.risk)
        if decision == Decision.DENY:
            return ToolResult(
                tool=tool.name,
                status="denied",
                message="Destructive tools are disabled in V1.",
            )
        try:
            arguments = tool.input_schema.model_validate(call.arguments)
        except ValidationError:
            return ToolResult(
                tool=tool.name, status="error", message="Invalid tool arguments."
            )
        if decision == Decision.CONFIRM and not (
            tool.risk == RiskLevel.INTERACTIVE and user_initiated
        ):
            # No confirm endpoint exists yet; pending actions cannot execute.
            return PendingAction(
                tool=tool.name,
                arguments=arguments.model_dump(mode="json"),
                risk=tool.risk,
            )
        try:
            return ToolResult(
                tool=tool.name, status="completed", data=tool.execute(arguments)
            )
        except ValueError as exc:
            return ToolResult(tool=tool.name, status="error", message=str(exc))
