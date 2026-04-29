"""Transform step executor for the worker."""

import json
import logging
import re
from typing import Any

from models import ExecutionStep
from transform.base import TRANSFORM_OPERATIONS

logger = logging.getLogger(__name__)


def execute_transform_step(
    step: ExecutionStep,
    template_parser: Any,
) -> tuple[None, bool, str, str]:
    """Execute a transform step.

    Returns:
        (None, success, logs, actual_value) — None because no NovaAct result.
    """
    operation_name = step.transform_operation
    if not operation_name or operation_name not in TRANSFORM_OPERATIONS:
        return None, False, f"Unknown transform operation: '{operation_name}'", ""

    if not step.capture_variable:
        return None, False, "capture_variable is required for transform steps", ""

    # Parse transform_args JSON
    try:
        raw_args = json.loads(step.transform_args) if step.transform_args else {}
    except (json.JSONDecodeError, TypeError) as exc:
        return None, False, f"Invalid transform_args JSON: {exc}", ""

    # Resolve {{ variables }} in all string-valued args
    resolved_args = _resolve_variables(raw_args, template_parser)

    # Execute the operation
    op = TRANSFORM_OPERATIONS[operation_name]
    try:
        result = op.validate_and_execute(resolved_args)
    except Exception as exc:
        return None, False, f"Transform '{operation_name}' failed: {exc}", ""

    actual_value = str(result)
    logger.info(f"Transform '{operation_name}' -> {step.capture_variable} = {actual_value}")
    return None, True, "", actual_value


def _resolve_variables(args: dict, template_parser: Any) -> dict:
    """Recursively resolve {{ var }} references in string values."""
    resolved = {}
    for key, value in args.items():
        if isinstance(value, str):
            resolved[key] = template_parser.parse_instruction(value)
        elif isinstance(value, list):
            resolved[key] = [
                template_parser.parse_instruction(v) if isinstance(v, str) else v
                for v in value
            ]
        else:
            resolved[key] = value
    return resolved
