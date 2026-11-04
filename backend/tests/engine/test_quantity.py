from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.calculation.engine.quantity import QuantityError, evaluate


@pytest.mark.parametrize(
    "expr,expected",
    [
        ("2*(3.5+4.2)*0.22", Decimal("3.388")),
        ("10/4", Decimal("2.5")),
        ("-3 + 5", Decimal("2")),
        ("2x3", Decimal("6")),
        ("1.1 × 3", Decimal("3.3")),
        ("0.1+0.2", Decimal("0.3")),  # Decimal, không phải float
    ],
)
def test_evaluate(expr, expected):
    assert evaluate(expr) == expected


def test_variables():
    assert evaluate("dai*rong*cao", {"dai": Decimal("2"), "rong": Decimal("3"), "cao": Decimal("0.5")}) == Decimal("3")
    with pytest.raises(QuantityError):
        evaluate("dai*2")


@pytest.mark.parametrize("expr", ["__import__('os')", "a.b", "f(1)", "2**10", "1 if 2 else 3", "[1]", "1<2", "", "1/0"])
def test_rejects_unsafe_or_invalid(expr):
    with pytest.raises(QuantityError):
        evaluate(expr)


@given(
    st.decimals(min_value=0, max_value=10**6, places=3, allow_nan=False, allow_infinity=False),
    st.decimals(min_value=0, max_value=10**6, places=3, allow_nan=False, allow_infinity=False),
)
def test_property_add_mul(a, b):
    assert evaluate(f"{a}+{b}") == a + b
    assert evaluate(f"({a})*({b})") == a * b
