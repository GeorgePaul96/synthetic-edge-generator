from edge_case_engine.mutators.scalar import ScalarMutator
from edge_case_engine.mutators.collection import ListMutator, DictMutator


class MutatorRegistry:
    def __init__(self, mutators=None):
        # Collection mutators are registered ahead of scalar; choose() picks among
        # whichever can_mutate the given value.
        self._mutators = mutators if mutators is not None else [
            ListMutator(), DictMutator(), ScalarMutator(),
        ]

    def applicable(self, handler, value):
        return [m for m in self._mutators if m.can_mutate(handler, value)]

    def choose(self, handler, value, rng):
        candidates = self.applicable(handler, value)
        return rng.choice(candidates) if candidates else None
