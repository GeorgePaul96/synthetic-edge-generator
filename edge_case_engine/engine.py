import random

from edge_case_engine.recipe import Recipe, materialize
from edge_case_engine.mutators.registry import MutatorRegistry


class EdgeCaseEngine:
    def __init__(self):
        self.mutation = MutatorRegistry()

    def _param_recipe(self, handler, master_rng, budget):
        seed = master_rng.getrandbits(64)
        return Recipe(descriptor=handler.descriptor(), seed=seed,
                      budget=budget.to_dict(), lineage=[])

    def generate_seeds(self, handlers, master_rng, budget, n_random=20):
        """Produce (input_tuple, [Recipe per param]) seeds.

        Strategy: n_random sampled combinations, one fresh recipe per parameter.
        Each recipe replays independently from its own per-parameter seed.
        """
        seeds = []
        seen = set()

        def add(recipes):
            inp = tuple(materialize(r) for r in recipes)
            key = repr(inp)
            if key in seen:
                return
            seen.add(key)
            seeds.append((inp, recipes))

        for _ in range(n_random):
            recipes = [self._param_recipe(h, master_rng, budget) for h in handlers]
            add(recipes)

        return seeds
