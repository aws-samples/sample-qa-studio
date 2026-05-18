"""Transform operation framework for QA Studio.

Each operation is a subclass of TransformOperation with a pydantic args model.
Operations are registered in TRANSFORM_OPERATIONS by name.
"""

from qa_studio_cli.runner.transform.base import TransformOperation, TRANSFORM_OPERATIONS
from qa_studio_cli.runner.transform.date_parser import DateParseError, parse_to_utc
from qa_studio_cli.runner.transform.math_evaluator import safe_eval_math
from qa_studio_cli.runner.transform.math_op import MathOperation
import qa_studio_cli.runner.transform.operations  # noqa: F401 — registers built-in numeric/string/etc. ops
import qa_studio_cli.runner.transform.date_ops    # noqa: F401 — registers date operations

__all__ = [
    "TransformOperation",
    "TRANSFORM_OPERATIONS",
    "DateParseError",
    "parse_to_utc",
    "safe_eval_math",
    "MathOperation",
]
