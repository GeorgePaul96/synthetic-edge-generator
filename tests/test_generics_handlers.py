import random

from edge_case_engine.budget import GenerationBudget
from type_handlers.scalars import IntegerHandler, StringHandler
from type_handlers.set_handler import SetHandler
from type_handlers.tuple_handler import TupleHandler
from type_handlers.literal_handler import LiteralHandler


def test_set_handler_generates_set_deterministically():
    h = SetHandler(IntegerHandler())
    b = GenerationBudget(max_list_length=4, max_total_nodes=50)
    v1 = h.generate(random.Random(5), GenerationBudget(max_list_length=4, max_total_nodes=50))
    v2 = h.generate(random.Random(5), b)
    assert isinstance(v1, set) and v1 == v2
    assert h.type_sig() == "set[int]"
    assert h.descriptor() == {"k": "set", "elem": {"k": "int"}}


def test_tuple_fixed_and_variadic():
    fixed = TupleHandler([IntegerHandler(), StringHandler()], variadic=False)
    v = fixed.generate(random.Random(1), GenerationBudget())
    assert isinstance(v, tuple) and len(v) == 2
    assert fixed.type_sig() == "tuple[int, str]"
    var = TupleHandler([IntegerHandler()], variadic=True)
    assert var.type_sig() == "tuple[int, ...]"
    assert isinstance(var.generate(random.Random(1), GenerationBudget()), tuple)


def test_literal_handler_picks_from_values():
    h = LiteralHandler(["a", "b", "c"])
    assert h.generate(random.Random(0), GenerationBudget()) in {"a", "b", "c"}
    assert list(h.edge_cases()) == ["a", "b", "c"]
    assert h.descriptor()["k"] == "literal"
