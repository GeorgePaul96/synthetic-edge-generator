import math
import random

from edge_case_engine.budget import GenerationBudget
from type_handlers.scalars import (
    FloatHandler, IntegerHandler, StringHandler, BoolHandler, NoneHandler,
)


def _take(it, n):
    out = []
    for i, x in enumerate(it):
        if i >= n:
            break
        out.append(x)
    return out


def test_float_generate_is_deterministic():
    b = GenerationBudget()
    v1 = FloatHandler().generate(random.Random(11), b)
    v2 = FloatHandler().generate(random.Random(11), b)
    assert (v1 == v2) or (math.isnan(v1) and math.isnan(v2))


def test_float_edge_cases_first_values_and_descriptor():
    first = _take(FloatHandler().edge_cases(), 3)
    assert 0.0 in first
    assert FloatHandler().descriptor() == {"k": "float"}
    assert FloatHandler().type_sig() == "float"


def test_int_bool_none_determinism_and_sigs():
    b = GenerationBudget()
    assert IntegerHandler().generate(random.Random(3), b) == IntegerHandler().generate(random.Random(3), b)
    assert BoolHandler().generate(random.Random(3), b) == BoolHandler().generate(random.Random(3), b)
    assert NoneHandler().generate(random.Random(3), b) is None
    assert (IntegerHandler().type_sig(), BoolHandler().type_sig(), NoneHandler().type_sig()) == ("int", "bool", "None")


def test_string_respects_budget_length():
    b = GenerationBudget(max_string_length=5)
    s = StringHandler().generate(random.Random(99), b)
    assert isinstance(s, str) and len(s) <= 5
    assert StringHandler().descriptor() == {"k": "str"}
