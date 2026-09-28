from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from permissions.policies import RiskLevel

Input = TypeVar("Input", bound=BaseModel)


class Tool(ABC, Generic[Input]):
    name: str
    description: str
    risk: RiskLevel
    input_schema: type[Input]

    @abstractmethod
    def execute(self, arguments: Input) -> dict[str, Any]:
        """Called only by deterministic permission enforcement."""
        raise NotImplementedError
