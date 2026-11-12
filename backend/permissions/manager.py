from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.pending_actions import PendingActionStore, StoredAction
    from agent.schemas import ExecutionRecord

from pydantic import ValidationError

from agent.schemas import PendingAction, ToolCall, ToolResult
from agent.tool_registry import ToolRegistry
from permissions.policies import Decision, RiskLevel, classify


class PermissionManager:
    def __init__(
        self, registry: ToolRegistry, *, allow_agent_reveal: bool = False
    ) -> None:
        self._registry = registry
        self._allow_agent_reveal = allow_agent_reveal

    def dispatch(
        self,
        call: ToolCall,
        *,
        user_initiated: bool = False,
        read_only: bool = False,
        agent_requested: bool = False,
        on_start: Callable[[], None] | None = None,
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
            tool.risk == RiskLevel.INTERACTIVE
            and (
                user_initiated
                or (
                    agent_requested
                    and self._allow_agent_reveal
                    and tool.name == "show_in_folder"
                )
            )
        ):
            # Ordinary dispatch never authorizes WRITE; stored writes use decide_write.
            return PendingAction(
                tool=tool.name,
                arguments=arguments.model_dump(mode="json"),
                risk=tool.risk,
            )
        if on_start is not None:
            on_start()
        try:
            return ToolResult(
                tool=tool.name, status="completed", data=tool.execute(arguments)
            )
        except ValueError as exc:
            return ToolResult(tool=tool.name, status="error", message=str(exc))

    def prepare_write(
        self,
        call: ToolCall,
        *,
        store: "PendingActionStore",
        conversation_id: str,
        owner: object,
    ) -> dict[str, Any]:
        from tools.mutations import WRITE_TOOLS

        tool = self._registry.get(call.tool)
        if call.tool not in WRITE_TOOLS or tool.risk != RiskLevel.WRITE:
            raise PermissionError("Not an approved write proposal.")
        arguments = tool.input_schema.model_validate(call.arguments)
        return store.prepare(call.tool, arguments.model_dump(), conversation_id, owner)

    def decide_write(
        self,
        *,
        store: "PendingActionStore",
        action_id: str,
        conversation_id: str,
        owner: object,
        cancel: bool = False,
    ) -> tuple["StoredAction", "ExecutionRecord"]:
        from agent.schemas import ExecutionRecord
        from agent.tool_execution import error
        from services.file_mutations import MutationError
        from tools.mutations import CreateFolderTool, MoveFileTool, RenameFileTool

        action = store.consume(action_id, conversation_id, owner, cancel=cancel)
        record = ExecutionRecord(
            tool_call_id=action_id, tool_name=action.plan.tool, arguments_validated=True
        )
        if cancel:
            record.result = error(
                "CANCELLED", "Action cancelled. No filesystem mutation occurred."
            )
            record.state = "rejected"
            return action, record
        try:
            tool = self._registry.get(action.plan.tool)
            if (
                type(tool) not in (CreateFolderTool, MoveFileTool, RenameFileTool)
                or tool.risk != RiskLevel.WRITE
            ):
                raise PermissionError("Write permission changed.")
            tool.input_schema.model_validate(action.arguments)
            store.service.revalidate(action.plan)
            if store.clock() >= action.expires:
                raise MutationError("EXPIRED", "Action expired before execution.")
            record.permission_approved = True
            record.executed = True
            data = store.service.execute(action.plan)
            action.status = "completed"
            record.state = "completed"
            record.result = {
                "success": True,
                "status": "SUCCESS"
                if data["index_synchronized"]
                else "INDEX_SYNC_FAILED",
                "data": data,
                "error_code": None,
                "error_message": None,
            }
        except Exception as exc:
            action.status = "failed"
            record.state = "failed" if record.executed else "rejected"
            code, message = (
                "OS_ERROR",
                "Operation failed. Review the filesystem and request a new action; no automatic retry occurred.",
            )
            if isinstance(exc, MutationError):
                code, message = exc.code, str(exc)
            elif isinstance(exc, PermissionError):
                code, message = (
                    "PERMISSION_DENIED",
                    "The path or operation is no longer allowed.",
                )
            elif isinstance(exc, FileNotFoundError):
                code, message = (
                    "NOT_FOUND",
                    "Source or directory no longer exists. Refresh the index.",
                )
            elif isinstance(exc, FileExistsError):
                code, message = (
                    "DESTINATION_EXISTS",
                    "Destination exists. Nothing was overwritten.",
                )
            elif isinstance(exc, NotImplementedError):
                code, message = (
                    "UNSUPPORTED_PLATFORM",
                    "Safe mutation is unsupported on this platform or filesystem.",
                )
            record.result = error(code, message)
        return action, record
