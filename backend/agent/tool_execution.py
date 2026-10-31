"""The model-facing subset of the existing registry; no dynamic resolution."""

import json
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent.schemas import ToolCall, ToolResult, ExecutionRecord, PendingAction
from agent.tool_registry import ToolRegistry, UnknownToolError
from permissions.manager import PermissionManager
from permissions.policies import RiskLevel
from services.file_actions import UnsupportedFileTypeError
from services.file_models import FileIdInput, SearchFilters
from services.llm.base import LLMToolCall, LLMToolDefinition
from tools.calculator import CalculateTool
from tools.files import GetFileInfoTool, SearchFilesTool, OpenFileTool, ShowInFolderTool

MAX_ARGUMENT_BYTES = 8192
MAX_RESULT_BYTES = 16384


class AgentSearchInput(SearchFilters):
    model_config = ConfigDict(extra="forbid", strict=True)
    q: str = Field(default="", alias="query", max_length=500)
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("modified_after", "modified_before", mode="before")
    @classmethod
    def iso_date(cls, value: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Dates must be ISO 8601 strings.")
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


class AgentFileInput(FileIdInput):
    model_config = ConfigDict(extra="forbid", strict=True)
    file_id: int = Field(gt=0, le=2**63 - 1)


class AgentCalculateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expression: str = Field(min_length=1, max_length=500)


# Exact implementation types prevent accidental exposure of a replacement tool
# under an approved name. Schemas narrow, but never broaden, registered inputs.
INTERACTION_TOOLS = frozenset({"open_file", "show_in_folder"})


def expected_risk(name: str) -> RiskLevel:
    return RiskLevel.INTERACTIVE if name in INTERACTION_TOOLS else RiskLevel.READ


APPROVED = {
    "search_files": (SearchFilesTool, AgentSearchInput),
    "get_file_info": (GetFileInfoTool, AgentFileInput),
    "calculate": (CalculateTool, AgentCalculateInput),
    "open_file": (OpenFileTool, AgentFileInput),
    "show_in_folder": (ShowInFolderTool, AgentFileInput),
}


def error(code: str, message: str) -> dict[str, Any]:
    return {
        "success": False,
        "status": {
            "EXECUTION_FAILURE": "TOOL_ERROR",
            "RESULT_TOO_LARGE": "EXECUTION_LIMIT_REACHED",
        }.get(code, code),
        "data": None,
        "error_code": code,
        "error_message": message,
    }


def encode(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":"))


def bounded_result(result: dict[str, Any]) -> str:
    try:
        data = result.get("data")
        while len(encode(result).encode()) > MAX_RESULT_BYTES:
            if (
                isinstance(data, dict)
                and isinstance(data.get("results"), list)
                and data["results"]
            ):
                data["results"].pop()
                data["truncated"] = True
                data["returned"] = len(data["results"])
            else:
                return encode(
                    error(
                        "RESULT_TOO_LARGE",
                        "Tool result exceeded the size limit; data was omitted.",
                    )
                )
        return encode(result)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return encode(
            error("EXECUTION_FAILURE", "Tool result could not be serialized.")
        )


class AgentToolExecutor:
    def __init__(self, registry: ToolRegistry, permissions: PermissionManager) -> None:
        self.registry = registry
        self.permissions = permissions

    def definitions(self, *, file_access: bool) -> list[LLMToolDefinition]:
        definitions = []
        for name, (implementation, schema) in APPROVED.items():
            if name != "calculate" and not file_access:
                continue
            try:
                tool = self.registry.get(name)
            except UnknownToolError:
                continue
            if type(tool) is implementation and tool.risk == expected_risk(name):
                definitions.append(
                    LLMToolDefinition(
                        name=name,
                        description=tool.description,
                        parameters=schema.model_json_schema(),
                    )
                )
        return definitions

    def execute_record(
        self,
        call: LLMToolCall,
        *,
        file_access: bool,
        history: list[ExecutionRecord] | None = None,
    ) -> ExecutionRecord:
        record = ExecutionRecord(tool_call_id=call.id, tool_name=call.name)
        record.result = json.loads(
            self.execute(call, file_access=file_access, record=record, history=history)
        )
        record.state = (
            ("completed" if record.result["success"] else "failed")
            if record.executed
            else "rejected"
        )
        logging.getLogger(__name__).info(
            "Tool outcome state=%s status=%s", record.state, record.result["status"]
        )
        return record

    def execute(
        self,
        call: LLMToolCall,
        *,
        file_access: bool,
        record: ExecutionRecord | None = None,
        history: list[ExecutionRecord] | None = None,
    ) -> str:
        try:
            return bounded_result(
                self._execute(
                    call, file_access=file_access, record=record, history=history
                )
            )
        except FileNotFoundError:
            return encode(
                error("NOT_FOUND", "Indexed file no longer exists or was not found.")
            )
        except UnsupportedFileTypeError:
            return encode(
                error("UNSUPPORTED_FILE_TYPE", "Opening this file type is disabled.")
            )
        except NotImplementedError:
            return encode(
                error("UNSUPPORTED_PLATFORM", "This interaction requires Windows.")
            )
        except PermissionError:
            return encode(
                error("PERMISSION_DENIED", "The requested path is not allowed.")
            )
        except OSError:
            return encode(
                error(
                    "OS_ERROR", "The operating system could not complete the request."
                )
            )
        except ValueError:
            return encode(
                error(
                    "INVALID_ARGUMENTS",
                    "The indexed path or tool arguments are invalid.",
                )
            )
        except Exception:
            return encode(
                error("EXECUTION_FAILURE", "The tool could not complete the request.")
            )

    def _execute(
        self,
        call: LLMToolCall,
        *,
        file_access: bool,
        record: ExecutionRecord | None = None,
        history: list[ExecutionRecord] | None = None,
    ) -> dict[str, Any]:
        try:
            tool = self.registry.get(call.name)
        except UnknownToolError:
            return error("UNKNOWN_TOOL", "The requested tool is not registered.")
        approved = APPROVED.get(call.name)
        if (
            approved is None
            or type(tool) is not approved[0]
            or tool.risk != expected_risk(call.name)
            or (call.name != "calculate" and not file_access)
        ):
            return error(
                "PERMISSION_DENIED", "This tool is not available for this request."
            )
        try:
            if len(call.arguments.encode()) > MAX_ARGUMENT_BYTES:
                raise ValueError
            # Strict JSON mode permits ISO dates but rejects stringified integers,
            # booleans, unknown fields and unexpected nested values.
            arguments = approved[1].model_validate_json(call.arguments, strict=True)
        except (ValidationError, ValueError, RecursionError):
            return error(
                "INVALID_ARGUMENTS", "Tool arguments do not match the supported schema."
            )

        def started() -> None:
            if record is not None:
                record.permission_approved = True
                record.executed = True
                record.state = "started"

        if record is not None:
            record.arguments_validated = True
        if call.name in INTERACTION_TOOLS:
            searches = [r for r in (history or []) if r.tool_name == "search_files"]
            if searches:
                latest = searches[-1].result
                data = latest.get("data") or {}
                matches = data.get("results", [])
                if not (
                    latest["success"]
                    and data.get("total") == 1
                    and len(matches) == 1
                    and matches[0].get("id") == arguments.file_id
                ):
                    return error(
                        "INVALID_ARGUMENTS",
                        "Please narrow the search to one matching file before requesting an interaction.",
                    )
        result = self.permissions.dispatch(
            ToolCall(tool=call.name, arguments=arguments.model_dump(mode="json")),
            read_only=call.name not in INTERACTION_TOOLS,
            **({"agent_requested": True} if call.name in INTERACTION_TOOLS else {}),
            **({"on_start": started} if record is not None else {}),
        )
        if isinstance(result, PendingAction) and call.name in INTERACTION_TOOLS:
            # Validation is read-only. Never turn provider prose into user_initiated.
            tool.service.validate_target(arguments.file_id, call.name)
            if record is not None:
                record.confirmation_required = True
            return error(
                "CONFIRMATION_REQUIRED",
                "This interaction requires confirmation. Nothing was opened or revealed. Use the file's Open or Show in Folder button in the desktop app.",
            )
        if not isinstance(result, ToolResult) or result.status == "denied":
            return error(
                "PERMISSION_DENIED", "Tool execution was denied by permission policy."
            )
        if result.status != "completed":
            return error(
                "INVALID_ARGUMENTS"
                if call.name in INTERACTION_TOOLS
                else "EXECUTION_FAILURE",
                "The tool could not complete the request (check arithmetic and filters).",
            )
        data = result.data
        if call.name == "search_files":
            data["returned"] = len(data["results"])
            data["truncated"] = data["total"] > data["offset"] + data["returned"]
        return {
            "success": True,
            "status": "NO_RESULTS"
            if call.name == "search_files" and data["total"] == 0
            else "SUCCESS",
            "data": data,
            "error_code": None,
            "error_message": None,
        }
