"""Math transform operation."""

from typing import ClassVar, Type

from pydantic import BaseModel

from transform.base import TransformOperation, register_operation
from transform.math_evaluator import safe_eval_math


class MathArgs(BaseModel):
    """Arguments for the math operation."""
    expression: str


class MathOperation(TransformOperation):
    """Evaluate an arithmetic expression.

    Variables must already be resolved to numeric values in the expression
    string (via TemplateParser) before this operation runs.
    """

    name: ClassVar[str] = "math"
    args_model: ClassVar[Type[BaseModel]] = MathArgs

    def execute(self, args: MathArgs) -> float | int:
        return safe_eval_math(args.expression)


register_operation(MathOperation())
