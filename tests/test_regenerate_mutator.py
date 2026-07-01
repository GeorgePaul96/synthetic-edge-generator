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


import copy
from dataclasses import dataclass
from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.recipe import Recipe, materialize
from type_handlers.resolver import TypeResolver


@dataclass
class _P:
    a: int
    b: int


def test_dataclass_instances_reach_the_function():
    engine = EdgeCaseEngine()
    handlers = [TypeResolver.resolve(_P)]
    budget = GenerationBudget()
    master = random.Random(0)
    base_input, base_recipes = engine.generate_seeds(handlers, master, budget, n_random=1)[0]
    received_dc = 0
    for _ in range(200):
        mutated, new_recipes, pi = engine.mutate_step(handlers, base_input, base_recipes, master, budget)
        if isinstance(mutated[0], _P):
            received_dc += 1
    assert received_dc > 0            # was 0 before RegenerateMutator


def test_live_equals_replay_for_regenerate_ops():
    h = TypeResolver.resolve(_P)
    budget = GenerationBudget()
    m = RegenerateMutator()
    for seed in range(100):
        rng = random.Random(seed)
        base_recipe = Recipe(h.descriptor(), rng.getrandbits(64), budget.to_dict(), [])
        base = materialize(base_recipe)
        op = m.mutate(h, base, rng, budget, path=[])
        live = apply_lineage_op(copy.deepcopy(base), op)
        replay = materialize(Recipe(h.descriptor(), base_recipe.seed, budget.to_dict(), [op]))
        assert values_equal(live, replay)
