from dataclasses import dataclass, asdict


@dataclass
class GenerationBudget:
    max_depth: int = 4
    max_list_length: int = 8
    max_dict_keys: int = 8
    max_string_length: int = 64
    probability_none: float = 0.1
    union_weights: tuple = ()
    max_total_nodes: int = 256

    def __post_init__(self):
        # Shared mutable accountant (one cell shared by all descendant budgets).
        self._accountant = [self.max_total_nodes]

    def child(self) -> "GenerationBudget":
        c = GenerationBudget(
            max_depth=self.max_depth - 1,
            max_list_length=self.max_list_length,
            max_dict_keys=self.max_dict_keys,
            max_string_length=self.max_string_length,
            probability_none=self.probability_none,
            union_weights=self.union_weights,
            max_total_nodes=self.max_total_nodes,
        )
        c._accountant = self._accountant  # share the same cell
        return c

    def spend(self, n: int = 1) -> bool:
        if self._accountant[0] < n:
            return False
        self._accountant[0] -= n
        return True

    def depth_exhausted(self) -> bool:
        return self.max_depth <= 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["union_weights"] = list(self.union_weights)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "GenerationBudget":
        d = dict(d)
        d["union_weights"] = tuple(d.get("union_weights", ()))
        return cls(**d)
