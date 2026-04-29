"""Safe AST-based arithmetic evaluator.

Parses an expression string with ``ast.parse(mode='eval')`` and walks
the tree with a strict whitelist.  Only numeric literals, the four
arithmetic operators (``+ - * / % **``), unary ``+``/``-``, and bare
variable names (looked up in a provided dict) are allowed.

Anything else — function calls, attribute access, subscripts,
comprehensions, imports, lambdas — raises ``UnsafeExpressionError``.
"""

import ast
import operator as _op
from typing import Any

_BINARY_OPS: dict[type, Any] = {
    ast.Add: _op.add,
    ast.Sub: _op.sub,
    ast.Mult: _op.mul,
    ast.Div: _op.truediv,
    ast.Mod: _op.mod,
    ast.Pow: _op.pow,
}

_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: _op.pos,
    ast.USub: _op.neg,
}

_MAX_EXPONENT = 1000
_MAX_RESULT = 1e308  # prevent intermediate results from blowing up memory


class UnsafeExpressionError(Exception):
    """Raised when an expression contains disallowed AST nodes."""


def safe_eval_math(expression: str, variables: dict[str, float | int] | None = None) -> float | int:
    """Evaluate a simple arithmetic expression safely.

    Args:
        expression: Arithmetic expression string (e.g. ``"price * 1.2"``).
        variables: Optional mapping of variable names to numeric values.

    Returns:
        The numeric result.

    Raises:
        UnsafeExpressionError: If the expression contains disallowed constructs.
        ValueError: If a referenced variable is not found.
        ZeroDivisionError: On division by zero.
    """
    variables = variables or {}
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(f"Invalid expression syntax: {exc}") from exc
    return _eval_node(tree.body, variables)


def _check_magnitude(value: float | int, context: str = "Result") -> float | int:
    """Reject intermediate results that would blow up memory."""
    if isinstance(value, (int, float)) and abs(value) > _MAX_RESULT:
        raise UnsafeExpressionError(f"{context} magnitude too large (abs > {_MAX_RESULT})")
    return value


def _eval_node(node: ast.AST, variables: dict[str, float | int]) -> float | int:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise UnsafeExpressionError(f"Non-numeric constant: {node.value!r}")
        if isinstance(node.value, (int, float)):
            return node.value
        raise UnsafeExpressionError(f"Non-numeric constant: {node.value!r}")

    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValueError(f"Unknown variable: '{node.id}'")
        val = variables[node.id]
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            raise ValueError(f"Variable '{node.id}' must be numeric, got {type(val).__name__}: {val!r}")
        return val

    if isinstance(node, ast.BinOp):
        op_fn = _BINARY_OPS.get(type(node.op))
        if op_fn is None:
            raise UnsafeExpressionError(f"Unsupported operator: {type(node.op).__name__}")
        left = _eval_node(node.left, variables)
        right = _eval_node(node.right, variables)
        if isinstance(node.op, ast.Pow):
            if isinstance(right, (int, float)) and abs(right) > _MAX_EXPONENT:
                raise UnsafeExpressionError(f"Exponent too large: {right} (max {_MAX_EXPONENT})")
            if isinstance(left, (int, float)) and abs(left) > _MAX_EXPONENT:
                raise UnsafeExpressionError(f"Base too large for exponentiation: {left}")
        result = op_fn(left, right)
        return _check_magnitude(result)

    if isinstance(node, ast.UnaryOp):
        op_fn = _UNARY_OPS.get(type(node.op))
        if op_fn is None:
            raise UnsafeExpressionError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand, variables))

    raise UnsafeExpressionError(f"Disallowed expression node: {type(node).__name__}")
