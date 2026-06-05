import math
from edge_case_engine.contracts import fuzz_contract


@fuzz_contract(allowed_exceptions=(ValueError,))
def divide(a, b):

    if not isinstance(a, (int, float)):
        raise TypeError("Numerator must be numeric")

    if not isinstance(b, (int, float)):
        raise TypeError("Denominator must be numeric")

    if math.isclose(b, 0.0, abs_tol=1e-12):
        raise ValueError("Division by zero or near zero")

    result = a / b

    if not math.isfinite(result):
        raise ValueError("Result is not finite")

    return result


@fuzz_contract(allowed_exceptions=(ValueError,))
def add(a: float, b: float):

    result = a + b

    if math.isnan(result):
        raise ValueError("Result is NaN")

    if math.isinf(result):
        raise ValueError("Result is infinite")

    return result


@fuzz_contract(allowed_exceptions=(ValueError,))
def multiply(a: float, b: float):

    result = a * b

    if math.isnan(result):
        raise ValueError("Result is NaN")

    if math.isinf(result):
        raise ValueError("Result is infinite")

    return result


@fuzz_contract(allowed_exceptions=(ValueError, TypeError))
def format_ratio(numerator: float, label: str) -> str:
    """Format a ratio with a label."""
    if not isinstance(numerator, (int, float)):
        raise TypeError("numerator must be numeric")
    if not isinstance(label, str):
        raise TypeError("label must be a string")
    ratio = numerator / 100.0
    return f"{label}: {ratio:.2%}"