import random

from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.budget import GenerationBudget
from edge_case_engine.recipe import materialize
from edge_case_engine.codec import values_equal
from type_handlers.scalars import IntegerHandler
from type_handlers.list_handler import ListHandler


def test_generate_seeds_recipes_replay_to_inputs():
    engine = EdgeCaseEngine()
    handlers = [IntegerHandler(), ListHandler(IntegerHandler())]
    seeds = engine.generate_seeds(handlers, random.Random(42), GenerationBudget(), n_random=5)
    assert seeds
    for input_tuple, recipes in seeds:
        assert len(recipes) == len(handlers)
        replayed = tuple(materialize(r) for r in recipes)
        assert values_equal(list(replayed), list(input_tuple))
