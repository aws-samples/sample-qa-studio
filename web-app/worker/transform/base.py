"""Base class and registry for transform operations."""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Type

from pydantic import BaseModel


class TransformOperation(ABC):
    """Base class for all transform operations."""

    name: ClassVar[str]
    args_model: ClassVar[Type[BaseModel]]

    @abstractmethod
    def execute(self, args: BaseModel) -> Any:
        """Execute the operation and return the result."""

    def validate_and_execute(self, raw_args: dict) -> Any:
        """Parse raw args dict into the typed model, then execute."""
        parsed = self.args_model(**raw_args)
        return self.execute(parsed)


# Global registry populated by register_operation()
TRANSFORM_OPERATIONS: dict[str, TransformOperation] = {}


def register_operation(op: TransformOperation) -> None:
    """Register a transform operation instance by its name."""
    TRANSFORM_OPERATIONS[op.name] = op
