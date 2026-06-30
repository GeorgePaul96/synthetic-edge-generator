import copy

from edge_case_engine.recipe import Recipe, materialize, apply_lineage_op
from edge_case_engine.mutators.registry import MutatorRegistry
from edge_case_engine.navigator import PathNavigator


class EdgeCaseEngine:
    def __init__(self):
        self.mutation = MutatorRegistry()
        self.navigator = PathNavigator()

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

    def mutate_step(self, handlers, base_input, base_recipes, rng, budget):
        """Mutate a randomly chosen parameter at a navigator-selected site.

        Returns (mutated_tuple, new_recipes, param_index) or None if no mutator applies.
        """
        pi = rng.randrange(len(handlers))
        path, h_sub, v_sub = self.navigator.select(handlers[pi], base_input[pi], rng)
        mutator = self.mutation.choose(h_sub, v_sub, rng)
        if mutator is None:
            return None
        op = mutator.mutate(h_sub, v_sub, rng, budget, path)
        new_param = apply_lineage_op(copy.deepcopy(base_input[pi]), op)
        mutated = tuple(new_param if j == pi else base_input[j] for j in range(len(base_input)))
        new_recipes = [Recipe.from_dict(r.to_dict()) for r in base_recipes]
        new_recipes[pi].lineage = list(base_recipes[pi].lineage) + [op]
        return mutated, new_recipes, pi
