import pytest
from pydantic import ValidationError

from agent.schemas import PendingAction, ToolCall
from agent.tool_registry import ToolRegistry, UnknownToolError
from permissions.manager import PermissionManager
from permissions.policies import Decision, RiskLevel, classify
from tools.calculator import CalculateTool


@pytest.mark.parametrize(("risk", "decision"), [
    (RiskLevel.READ, Decision.ALLOW),
    (RiskLevel.WRITE, Decision.CONFIRM),
    (RiskLevel.DESTRUCTIVE, Decision.DENY),
])
def test_classification(risk, decision):
    assert classify(risk) == decision


@pytest.mark.parametrize("risk", [RiskLevel.WRITE, RiskLevel.DESTRUCTIVE])
def test_guard_never_executes_unapproved_tool(risk):
    class SpyTool(CalculateTool):
        def execute(self, arguments):
            pytest.fail("Unapproved tool executed")

    tool = SpyTool()
    tool.risk = risk
    registry = ToolRegistry()
    registry.register(tool)
    result = PermissionManager(registry).dispatch(
        ToolCall(tool="calculate", arguments={"operation": "add", "operands": [1, 2]})
    )
    if risk == RiskLevel.WRITE:
        assert isinstance(result, PendingAction)
        assert result.risk == RiskLevel.WRITE
    else:
        assert result.status == "denied"


def test_read_dispatch_and_validation():
    registry = ToolRegistry()
    registry.register(CalculateTool())
    manager = PermissionManager(registry)
    result = manager.dispatch(ToolCall(tool="calculate", arguments={"operation": "add", "operands": [1, 2]}))
    assert result.status == "completed"
    assert result.data == {"value": 3}
    assert manager.dispatch(ToolCall(tool="calculate")).status == "error"
    with pytest.raises(UnknownToolError):
        manager.dispatch(ToolCall(tool="shell"))
    with pytest.raises(ValidationError):
        ToolCall(tool="calculate", risk="READ", confirmed=True)
