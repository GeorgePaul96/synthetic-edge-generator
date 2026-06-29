import random
from typing import Any, Iterator

from edge_case_engine.budget import GenerationBudget


class Handler:
    """Generates and describes values for ONE type node. No mutation logic here."""

    def generate(self, rng: random.Random, budget: GenerationBudget) -> Any:
        """Sample exactly one value. MUST be a pure function of (rng state, budget)."""
        raise NotImplementedError

    def edge_cases(self) -> Iterator[Any]:
        """Yield boundary/extreme values, highest-value first, lazily."""
        raise NotImplementedError

    def type_sig(self) -> str:
        """Stable human-readable signature, e.g. 'list[dict[str, int]]'."""
        raise NotImplementedError

    def descriptor(self) -> dict:
        """Serializable structured descriptor the resolver can rebuild from."""
        raise NotImplementedError
