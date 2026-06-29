from edge_case_engine.mutators.base import Mutator
from edge_case_engine.recipe import LineageOp
from edge_case_engine.codec import encode

_POOL = [None, "synthedge", float("inf"), float("nan"), 0, -1, 1e308, True]


class ScalarMutator(Mutator):
    def can_mutate(self, handler, value) -> bool:
        return not isinstance(value, (list, dict))

    def mutate(self, handler, value, rng, budget, path):
        new_value = rng.choice(_POOL)
        return new_value, LineageOp(op="scalar.replace", path=list(path),
                                    args={"value": encode(new_value)})
