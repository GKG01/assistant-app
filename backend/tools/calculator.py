import math
import ast
import operator
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from permissions.policies import RiskLevel
from tools.base import Tool


class CalculateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expression: str | None = Field(default=None, min_length=1, max_length=500)
    operation: Literal["add", "subtract", "multiply", "divide"] | None = None
    operands: list[FiniteFloat] | None = Field(
        default=None, min_length=2, max_length=100
    )

    @model_validator(mode="after")
    def one_form(self) -> Self:
        if self.expression is not None:
            if self.operation is not None or self.operands is not None:
                raise ValueError("Use expression or operation/operands, not both.")
        elif self.operation is None or self.operands is None:
            raise ValueError("An expression or operation/operands is required.")
        return self


def arithmetic(expression: str) -> float:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, RecursionError):
        raise ValueError("Invalid arithmetic expression.") from None
    if sum(1 for _ in ast.walk(tree)) > 100:
        raise ValueError("Expression is too complex.")
    operations = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }

    def visit(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = float(node.value)
        elif isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and type(node.op) in operations:
            try:
                value = operations[type(node.op)](visit(node.left), visit(node.right))
            except (ZeroDivisionError, OverflowError):
                raise ValueError(
                    "Unsafe arithmetic operation (including division by zero)."
                ) from None
        else:
            raise ValueError("Only numeric literals and basic arithmetic are allowed.")
        if not math.isfinite(value) or abs(value) > 1e100:
            raise ValueError("Number is outside the supported finite range.")
        return value

    return visit(tree.body)


class CalculateTool(Tool[CalculateInput]):
    name = "calculate"
    description = "Calculate basic arithmetic: +, -, *, /, parentheses and decimals."
    risk = RiskLevel.READ
    input_schema = CalculateInput

    def execute(self, arguments: CalculateInput) -> dict[str, float]:
        if arguments.expression is not None:
            return {"value": arithmetic(arguments.expression)}
        assert arguments.operands is not None
        result = arguments.operands[0]
        for value in arguments.operands[1:]:
            match arguments.operation:
                case "add":
                    result += value
                case "subtract":
                    result -= value
                case "multiply":
                    result *= value
                case "divide":
                    if value == 0:
                        raise ValueError("Division by zero is not allowed.")
                    result /= value
        if not math.isfinite(result):
            raise ValueError("Result is outside the finite numeric range.")
        return {"value": result}
