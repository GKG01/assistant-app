from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from permissions.policies import RiskLevel


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


ConversationId = Annotated[
    str,
    Field(
        strict=True,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    ),
]


class ClearConversationRequest(Contract):
    conversation_id: ConversationId


class AgentRequest(Contract):
    conversation_id: ConversationId | None = None
    message: str = Field(min_length=1, max_length=10000)

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank.")
        return value.strip()


class ToolCall(Contract):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(Contract):
    tool: str
    status: Literal["completed", "denied", "error"]
    data: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class PendingAction(Contract):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tool: str
    arguments: dict[str, Any]
    risk: RiskLevel
    status: Literal["pending"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionRecord(Contract):
    tool_call_id: str
    tool_name: str
    executed: bool = False
    arguments_validated: bool = False
    permission_approved: bool = False
    confirmation_required: bool = False
    state: Literal["requested", "rejected", "started", "completed", "failed"] = (
        "requested"
    )
    result: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(Contract):
    conversation_id: ConversationId | None = None
    message: str
    result: ToolResult | None = None
    pending_action: PendingAction | None = None
    tool_executions: list[ExecutionRecord] = Field(default_factory=list)
