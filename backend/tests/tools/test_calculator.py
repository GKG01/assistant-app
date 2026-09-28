import pytest
from pydantic import ValidationError

from tools.calculator import CalculateInput, CalculateTool


@pytest.mark.parametrize(("operation", "operands", "expected"), [
    ("add", [2, 3, 4], 9),
    ("subtract", [10, 3, 2], 5),
    ("multiply", [2, 3, 4], 24),
    ("divide", [20, 2, 5], 2),
])
def test_calculate(operation, operands, expected):
    assert CalculateTool().execute(CalculateInput(operation=operation, operands=operands)) == {"value": expected}


@pytest.mark.parametrize("arguments", [
    {"operation": "add", "operands": [1]},
    {"operation": "add", "operands": [True, 2]},
    {"operation": "add", "operands": [float("inf"), 2]},
    {"operation": "eval", "operands": [1, 2]},
    {"operation": "add", "operands": [1, 2], "code": "anything"},
])
def test_invalid_arguments(arguments):
    with pytest.raises(ValidationError):
        CalculateInput.model_validate(arguments)


def test_divide_by_zero():
    with pytest.raises(ValueError, match="zero"):
        CalculateTool().execute(CalculateInput(operation="divide", operands=[1, 0]))


def test_overflow():
    with pytest.raises(ValueError, match="finite"):
        CalculateTool().execute(CalculateInput(operation="multiply", operands=[1e308, 10]))
