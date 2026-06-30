class Mutator:
    def can_mutate(self, handler, value) -> bool:
        raise NotImplementedError

    def mutate(self, handler, value, rng, budget, path):
        """Return a LineageOp (concrete, encoded effect at `path`). No value is returned;
        the engine derives the value by applying the op via recipe.apply_lineage_op."""
        raise NotImplementedError
