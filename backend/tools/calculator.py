import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from permissions.policies import RiskLevel
from tools.base import Tool


class CalculateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation: Literal["add", "subtract", "multiply", "divide"]
    operands: list[FiniteFloat] = Field(min_length=2, max_length=100)


class CalculateTool(Tool[CalculateInput]):
    name = "calculate"
    description = "Apply basic arithmetic to 2–100 finite numbers, left to right."
    risk = RiskLevel.READ
    input_schema = CalculateInput

    def execute(self, arguments: CalculateInput) -> dict[str, float]:
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
