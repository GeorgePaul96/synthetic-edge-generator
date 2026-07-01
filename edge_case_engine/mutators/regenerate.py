from edge_case_engine.mutators.base import Mutator
from edge_case_engine.recipe import LineageOp
from edge_case_engine.codec import encode


class RegenerateMutator(Mutator):
    """Replace a leaf value with a fresh, handler-generated instance of the same type.

    Emitted as a scalar.replace op so replay reuses the existing apply path.
    """

    def can_mutate(self, handler, value) -> bool:
        return not isinstance(value, (list, dict))   # list/dict stay structurally mutated

    def mutate(self, handler, value, rng, budget, path):
        fresh = handler.generate(rng, budget.child())
        return LineageOp(op="scalar.replace", path=list(path), args={"value": encode(fresh)})
