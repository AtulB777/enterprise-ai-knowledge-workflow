"""Real security test: safe_eval must never execute anything beyond basic
arithmetic — no name lookups, calls, attribute access, or imports.
"""

import pytest

from app.services.agents.tools.safe_eval import UnsafeExpressionError, safe_eval


def test_basic_arithmetic() -> None:
    assert safe_eval("2 + 3") == 5
    assert safe_eval("10 - 4") == 6
    assert safe_eval("3 * 7") == 21
    assert safe_eval("10 / 4") == 2.5
    assert safe_eval("2 ** 10") == 1024
    assert safe_eval("10 % 3") == 1


def test_operator_precedence_and_parentheses() -> None:
    assert safe_eval("2 + 3 * 4") == 14
    assert safe_eval("(2 + 3) * 4") == 20


def test_unary_operators() -> None:
    assert safe_eval("-5") == -5
    assert safe_eval("-(3 + 2)") == -5
    assert safe_eval("+5") == 5


def test_division_by_zero_raises_unsafe_expression_error() -> None:
    with pytest.raises(UnsafeExpressionError, match="Division by zero"):
        safe_eval("1 / 0")


def test_syntax_error_raises_unsafe_expression_error() -> None:
    with pytest.raises(UnsafeExpressionError):
        safe_eval("2 +")


@pytest.mark.parametrize(
    "malicious_expression",
    [
        "__import__('os').system('echo pwned')",
        "open('/etc/passwd').read()",
        "[x for x in ().__class__.__base__.__subclasses__()]",
        "().__class__",
        "exec('1')",
        "eval('1')",
        "os.system('ls')",
        "(1).bit_length()",
        "[1, 2, 3]",
        "{'a': 1}",
        "lambda: 1",
        "1 if True else 2",
    ],
)
def test_rejects_anything_beyond_arithmetic(malicious_expression: str) -> None:
    with pytest.raises(UnsafeExpressionError):
        safe_eval(malicious_expression)


def test_rejects_string_constants() -> None:
    with pytest.raises(UnsafeExpressionError):
        safe_eval("'a' + 'b'")


def test_rejects_boolean_constants() -> None:
    # bool is technically a subclass of int in Python - explicitly rejected
    # so True/False can't sneak through the isinstance(value, int) check.
    with pytest.raises(UnsafeExpressionError):
        safe_eval("True")
