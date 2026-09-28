import pytest

from agent.tool_registry import ToolRegistry, UnknownToolError
from tools.calculator import CalculateTool


def test_explicit_registration():
    registry = ToolRegistry()
    assert registry.descriptions() == []
    tool = CalculateTool()
    registry.register(tool)
    assert registry.get("calculate") is tool
    assert registry.descriptions()[0]["input_schema"]["type"] == "object"
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)


def test_unknown_tool_rejected():
    with pytest.raises(UnknownToolError):
        ToolRegistry().get("shell")
