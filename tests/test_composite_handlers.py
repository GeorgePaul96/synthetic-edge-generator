import random

from edge_case_engine.budget import GenerationBudget
from type_handlers.scalars import IntegerHandler, StringHandler
from type_handlers.optional_handler import OptionalHandler
from type_handlers.union_handler import UnionHandler
from type_handlers.list_handler import ListHandler
from type_handlers.dict_handler import DictHandler


def test_optional_can_yield_none_and_inner():
    h = OptionalHandler(IntegerHandler())
    b = GenerationBudget(probability_none=1.0)
    assert h.generate(random.Random(1), b) is None
    b2 = GenerationBudget(probability_none=0.0)
    assert isinstance(h.generate(random.Random(1), b2), int)
    assert h.descriptor() == {"k": "optional", "inner": {"k": "int"}}
    assert h.type_sig() == "Optional[int]"


def test_union_generates_one_of_the_options():
    h = UnionHandler([IntegerHandler(), StringHandler()])
    b = GenerationBudget()
    vals = [h.generate(random.Random(s), b) for s in range(20)]
    assert any(isinstance(v, int) for v in vals)
    assert any(isinstance(v, str) for v in vals)
    assert h.descriptor() == {"k": "union", "options": [{"k": "int"}, {"k": "str"}]}
    assert h.type_sig() == "Union[int, str]"


def test_list_generates_within_budget_and_is_deterministic():
    h = ListHandler(IntegerHandler())
    b1 = GenerationBudget(max_list_length=4, max_total_nodes=100)
    b2 = GenerationBudget(max_list_length=4, max_total_nodes=100)
    v1 = h.generate(random.Random(5), b1)
    v2 = h.generate(random.Random(5), b2)
    assert v1 == v2
    assert isinstance(v1, list) and len(v1) <= 4
    assert h.type_sig() == "list[int]"


def test_list_stops_when_depth_exhausted():
    h = ListHandler(IntegerHandler())
    b = GenerationBudget(max_depth=0)
    assert h.generate(random.Random(5), b) == []


def test_dict_generates_within_budget_and_is_deterministic():
    h = DictHandler(StringHandler(), IntegerHandler())
    b1 = GenerationBudget(max_dict_keys=3, max_total_nodes=100)
    b2 = GenerationBudget(max_dict_keys=3, max_total_nodes=100)
    v1 = h.generate(random.Random(8), b1)
    v2 = h.generate(random.Random(8), b2)
    assert v1 == v2
    assert isinstance(v1, dict) and len(v1) <= 3
    assert h.type_sig() == "dict[str, int]"
    assert h.descriptor() == {"k": "dict", "key": {"k": "str"}, "val": {"k": "int"}}
