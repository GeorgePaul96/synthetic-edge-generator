class Mutator:
    def can_mutate(self, handler, value) -> bool:
        raise NotImplementedError

    def mutate(self, handler, value, rng, budget, path):
        """Return (new_value, LineageOp). path locates `value` within the root input."""
        raise NotImplementedError
