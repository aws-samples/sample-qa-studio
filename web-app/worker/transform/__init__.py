"""Transform operation framework for QA Studio.

Each operation is a subclass of TransformOperation with a pydantic args model.
Operations are registered in TRANSFORM_OPERATIONS by name.
"""

from transform.base import TransformOperation, TRANSFORM_OPERATIONS
from transform.date_parser import DateParseError, parse_to_utc
from transform.math_evaluator import safe_eval_math
from transform.math_op import MathOperation
import transform.operations  # noqa: F401 — registers built-in numeric/string/etc. ops
import transform.date_ops    # noqa: F401 — registers date operations

__all__ = [
    "TransformOperation",
    "TRANSFORM_OPERATIONS",
    "DateParseError",
    "parse_to_utc",
    "safe_eval_math",
    "MathOperation",
]
