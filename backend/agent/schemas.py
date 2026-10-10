from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from permissions.policies import RiskLevel


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRequest(Contract):
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


class AgentResponse(Contract):
    message: str
    result: ToolResult | None = None
    pending_action: PendingAction | None = None
