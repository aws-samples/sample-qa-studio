"""Transform operation framework for QA Studio.

Each operation is a subclass of TransformOperation with a pydantic args model.
Operations are registered in TRANSFORM_OPERATIONS by name.
"""

from qa_studio_cli.runner.transform.base import TransformOperation, TRANSFORM_OPERATIONS
from qa_studio_cli.runner.transform.math_evaluator import safe_eval_math
from qa_studio_cli.runner.transform.math_op import MathOperation
import qa_studio_cli.runner.transform.operations  # noqa: F401 — registers all built-in operations

__all__ = [
    "TransformOperation",
    "TRANSFORM_OPERATIONS",
    "safe_eval_math",
    "MathOperation",
]
