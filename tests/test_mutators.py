import random

from edge_case_engine.budget import GenerationBudget
from edge_case_engine.mutators.scalar import ScalarMutator
from edge_case_engine.mutators.collection import ListMutator, DictMutator
from type_handlers.scalars import IntegerHandler, StringHandler
from type_handlers.list_handler import ListHandler
from type_handlers.dict_handler import DictHandler


def test_scalar_mutator_replaces_and_records_op():
    m = ScalarMutator()
    h = IntegerHandler()
    new_value, op = m.mutate(h, 5, random.Random(2), GenerationBudget(), path=[])
    assert op.op == "scalar.replace"
    assert op.path == []
    assert "value" in op.args


def test_list_mutator_changes_list_and_records_op():
    h = ListHandler(IntegerHandler())
    new_value, op = ListMutator().mutate(h, [1, 2, 3], random.Random(4), GenerationBudget(), path=[])
    assert op.op.startswith("list.")
    assert isinstance(new_value, list)


def test_dict_mutator_changes_dict_and_records_op():
    h = DictHandler(StringHandler(), IntegerHandler())
    new_value, op = DictMutator().mutate(h, {"a": 1}, random.Random(4), GenerationBudget(), path=[])
    assert op.op.startswith("dict.")
    assert isinstance(new_value, dict)
