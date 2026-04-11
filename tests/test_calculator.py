"""
tests/test_calculator.py
========================
Tests unitaires pour tools/calculator.py
"""

import pytest
from tools.calculator import Calculator, CalculatorError


@pytest.fixture
def calc():
    """Calculatrice pour les tests."""
    return Calculator()


def test_addition(calc):
    assert calc.evaluate("2 + 3") == 5.0


def test_subtraction(calc):
    assert calc.evaluate("10 - 4") == 6.0


def test_multiplication(calc):
    assert calc.evaluate("3 * 7") == 21.0


def test_division(calc):
    assert calc.evaluate("15 / 3") == 5.0


def test_power(calc):
    assert calc.evaluate("2 ** 8") == 256.0


def test_modulo(calc):
    assert calc.evaluate("10 % 3") == 1.0


def test_floor_division(calc):
    assert calc.evaluate("10 // 3") == 3.0


def test_parentheses(calc):
    assert calc.evaluate("(2 + 3) * 4") == 20.0


def test_negative_number(calc):
    assert calc.evaluate("-5 + 10") == 5.0


def test_float(calc):
    assert calc.evaluate("3.14 * 2") == pytest.approx(6.28)


def test_complex_expression(calc):
    assert calc.evaluate("2 + 3 * 4 - 1") == 13.0


def test_division_by_zero(calc):
    with pytest.raises(CalculatorError):
        calc.evaluate("10 / 0")


def test_empty_expression(calc):
    with pytest.raises(CalculatorError):
        calc.evaluate("")


def test_invalid_expression(calc):
    with pytest.raises(CalculatorError):
        calc.evaluate("abc + 1")


def test_dangerous_code_blocked(calc):
    """Le code dangereux doit être bloqué."""
    with pytest.raises(CalculatorError):
        calc.evaluate("__import__('os').system('echo hack')")


def test_format_result_integer(calc):
    assert calc.format_result(6.0) == "6"


def test_format_result_float(calc):
    assert calc.format_result(3.14) == "3.14"
