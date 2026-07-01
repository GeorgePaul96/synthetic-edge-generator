from edge_case_engine.mutators.scalar import ScalarMutator
from edge_case_engine.mutators.collection import ListMutator, DictMutator
from edge_case_engine.mutators.regenerate import RegenerateMutator


class MutatorRegistry:
    def __init__(self, mutators=None):
        # Collection mutators keep list/dict structural; RegenerateMutator and ScalarMutator
        # both apply to leaves, so choose() mixes fresh same-type instances with pool scalars.
        self._mutators = mutators if mutators is not None else [
            ListMutator(), DictMutator(), RegenerateMutator(), ScalarMutator(),
        ]

    def applicable(self, handler, value):
        return [m for m in self._mutators if m.can_mutate(handler, value)]

    def choose(self, handler, value, rng):
        candidates = self.applicable(handler, value)
        return rng.choice(candidates) if candidates else None
