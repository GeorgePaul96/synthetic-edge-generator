import random

from edge_case_engine.budget import GenerationBudget
from edge_case_engine.recipe import LineageOp, apply_lineage_op
from edge_case_engine.codec import values_equal, decode
from edge_case_engine.mutators.regenerate import RegenerateMutator
from edge_case_engine.mutators.registry import MutatorRegistry
from type_handlers.scalars import IntegerHandler
from type_handlers.tuple_handler import TupleHandler
from type_handlers.list_handler import ListHandler


def test_regenerate_produces_same_type_and_is_applyable():
    h = TupleHandler([IntegerHandler(), IntegerHandler()], variadic=False)
    op = RegenerateMutator().mutate(h, (1, 2), random.Random(3), GenerationBudget(), path=[])
    assert isinstance(op, LineageOp) and op.op == "scalar.replace"
    applied = apply_lineage_op((9, 9), op)
    assert isinstance(applied, tuple)                 # type preserved
    assert values_equal(applied, decode(op.args["value"]))


def test_regenerate_skips_list_and_dict():
    m = RegenerateMutator()
    assert m.can_mutate(IntegerHandler(), 5) is True
    assert m.can_mutate(ListHandler(IntegerHandler()), [1]) is False


def test_registry_includes_regenerate():
    kinds = {type(m).__name__ for m in MutatorRegistry()._mutators}
    assert "RegenerateMutator" in kinds
