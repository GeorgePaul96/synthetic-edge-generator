import random

from edge_case_engine.budget import GenerationBudget
from edge_case_engine.recipe import LineageOp
from edge_case_engine.mutators.scalar import ScalarMutator
from edge_case_engine.mutators.collection import ListMutator, DictMutator
from type_handlers.scalars import IntegerHandler, StringHandler
from type_handlers.list_handler import ListHandler
from type_handlers.dict_handler import DictHandler


def test_scalar_mutator_returns_lineage_op():
    op = ScalarMutator().mutate(IntegerHandler(), 5, random.Random(2), GenerationBudget(), path=[])
    assert isinstance(op, LineageOp) and op.op == "scalar.replace" and op.path == []
    assert "value" in op.args


def test_list_mutator_returns_lineage_op_with_path():
    op = ListMutator().mutate(ListHandler(IntegerHandler()), [1, 2, 3],
                              random.Random(4), GenerationBudget(), path=[["list", 0]])
    assert isinstance(op, LineageOp) and op.op.startswith("list.") and op.path == [["list", 0]]


def test_dict_mutator_returns_lineage_op():
    op = DictMutator().mutate(DictHandler(StringHandler(), IntegerHandler()), {"a": 1},
                              random.Random(4), GenerationBudget(), path=[])
    assert isinstance(op, LineageOp) and op.op.startswith("dict.")
