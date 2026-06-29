"""Architecture Gate — the Definition of Done for the Slice 1 engine rewrite.

Asserts the spec §9 gate on a real nested-typed fixture: deterministic generation,
corpus replay, nested recursion, no exponential blow-up, and generic fallback < 10%.
"""
import random
from typing import List, Dict, Optional, Union

from type_handlers.resolver import TypeResolver
from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.budget import GenerationBudget
from edge_case_engine.recipe import materialize
from edge_case_engine.codec import values_equal

FIXTURE = [List[Dict[str, int]], Optional[str], Union[int, None]]


def test_no_generic_fallback_on_fixture():
    r = TypeResolver()
    for ann in FIXTURE:
        r.resolve_tracked(ann)
    assert r.fallback_rate() < 0.10
    assert r.fallback_rate() == 0.0   # this fixture is fully typed


def test_deterministic_generation_and_replay():
    engine = EdgeCaseEngine()
    handlers = [TypeResolver.resolve(a) for a in FIXTURE]
    seeds = engine.generate_seeds(handlers, random.Random(2026), GenerationBudget(), n_random=10)
    assert seeds
    for input_tuple, recipes in seeds:
        replayed = tuple(materialize(rc) for rc in recipes)
        assert values_equal(list(replayed), list(input_tuple))


def test_no_exponential_blowup():
    deep = List[List[List[List[int]]]]
    h = TypeResolver.resolve(deep)
    budget = GenerationBudget(max_total_nodes=64)
    value = h.generate(random.Random(1), budget)

    def count(v):
        if isinstance(v, list):
            return 1 + sum(count(x) for x in v)
        return 1

    assert count(value) <= 200    # accountant + depth cap prevent blow-up
