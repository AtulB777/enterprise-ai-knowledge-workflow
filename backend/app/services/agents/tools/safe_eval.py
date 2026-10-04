"""Safe arithmetic expression evaluation.

Deliberately NOT `eval()` — this parses the expression into an AST and only
walks a small allowlist of node types (numeric literals, +, -, *, /, %, **,
unary +/-). There is no path to name lookups, attribute access, function
calls, or imports, because those AST node types are never matched — an
expression containing them raises ValueError rather than falling through to
some default behavior.
"""

import ast
import operator
from collections.abc import Callable

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


class UnsafeExpressionError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def safe_eval(expression: str) -> float:
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(f"Not a valid expression: {exc}") from exc
    return _eval_node(parsed.body)


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise UnsafeExpressionError(f"Unsupported constant: {node.value!r}")
        return float(node.value)

    if isinstance(node, ast.BinOp):
        binary_op_fn = _BINARY_OPERATORS.get(type(node.op))
        if binary_op_fn is None:
            raise UnsafeExpressionError(f"Unsupported operator: {type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        try:
            return binary_op_fn(left, right)
        except ZeroDivisionError as exc:
            raise UnsafeExpressionError("Division by zero.") from exc

    if isinstance(node, ast.UnaryOp):
        unary_op_fn = _UNARY_OPERATORS.get(type(node.op))
        if unary_op_fn is None:
            raise UnsafeExpressionError(f"Unsupported unary operator: {type(node.op).__name__}")
        return unary_op_fn(_eval_node(node.operand))

    # Anything else — Name, Call, Attribute, Subscript, Lambda, comprehensions,
    # etc. — is rejected explicitly rather than silently ignored.
    raise UnsafeExpressionError(f"Unsupported expression element: {type(node).__name__}")
