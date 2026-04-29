"""Transform operation framework for QA Studio.

Each operation is a subclass of TransformOperation with a pydantic args model.
Operations are registered in TRANSFORM_OPERATIONS by name.
"""

from transform.base import TransformOperation, TRANSFORM_OPERATIONS
from transform.math_evaluator import safe_eval_math
from transform.math_op import MathOperation
import transform.operations  # noqa: F401 — registers all built-in operations

__all__ = [
    "TransformOperation",
    "TRANSFORM_OPERATIONS",
    "safe_eval_math",
    "MathOperation",
]
