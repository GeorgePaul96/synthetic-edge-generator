import random

from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.budget import GenerationBudget
from type_handlers.scalars import IntegerHandler, StringHandler, FloatHandler


def test_mutate_step_covers_all_params():
    engine = EdgeCaseEngine()
    handlers = [IntegerHandler(), StringHandler(), FloatHandler()]
    budget = GenerationBudget()
    master = random.Random(7)
    seeds = engine.generate_seeds(handlers, master, budget, n_random=1)
    base_input, base_recipes = seeds[0]
    touched = set()
    for _ in range(200):
        res = engine.mutate_step(handlers, base_input, base_recipes, master, budget)
        if res is not None:
            touched.add(res[2])
    assert touched == {0, 1, 2}


def test_mutate_step_recipe_replays_to_mutated_param():
    from edge_case_engine.recipe import materialize
    from edge_case_engine.codec import values_equal
    engine = EdgeCaseEngine()
    handlers = [IntegerHandler()]
    budget = GenerationBudget()
    master = random.Random(3)
    base_input, base_recipes = engine.generate_seeds(handlers, master, budget, n_random=1)[0]
    res = engine.mutate_step(handlers, base_input, base_recipes, master, budget)
    assert res is not None
    mutated, new_recipes, pi = res
    assert values_equal(materialize(new_recipes[pi]), mutated[pi])
