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


# ---------------------------------------------------------------------------
# Architecture Gate v2 (Slice 2): deep mutation + generics
# ---------------------------------------------------------------------------
import copy
from typing import Set, Tuple, Literal
from edge_case_engine.navigator import PathNavigator
from edge_case_engine.recipe import Recipe, apply_lineage_op, _get_node
from edge_case_engine.mutators.registry import MutatorRegistry

GENERICS_FIXTURE = [Set[int], Tuple[int, str], Tuple[int, ...], Literal["a", "b"],
                    List[Dict[str, List[int]]]]


def test_generics_no_fallback_and_roundtrip():
    r = TypeResolver()
    for ann in GENERICS_FIXTURE:
        r.resolve_tracked(ann)
    assert r.fallback_rate() == 0.0
    for ann in GENERICS_FIXTURE:
        h = TypeResolver.resolve(ann)
        assert TypeResolver.from_descriptor(h.descriptor()).type_sig() == h.type_sig()


def test_live_equals_replay_for_nested_mutation():
    h = TypeResolver.resolve(List[Dict[str, int]])
    budget = GenerationBudget()
    nav = PathNavigator()
    reg = MutatorRegistry()
    checked = 0
    for seed in range(300):
        rng = random.Random(seed)
        base_recipe = Recipe(h.descriptor(), rng.getrandbits(64), budget.to_dict(), [])
        base = materialize(base_recipe)
        path, h_sub, v_sub = nav.select(h, base, rng)
        mut = reg.choose(h_sub, v_sub, rng)
        if mut is None:
            continue
        op = mut.mutate(h_sub, v_sub, rng, budget, path)
        live = apply_lineage_op(copy.deepcopy(base), op)
        replay = materialize(Recipe(h.descriptor(), base_recipe.seed, budget.to_dict(), [op]))
        assert values_equal(live, replay)
        if path:
            checked += 1
    assert checked > 0   # we actually exercised some nested-path mutations


def test_navigator_soundness_on_nested_fixture():
    h = TypeResolver.resolve(List[Dict[str, List[int]]])
    budget = GenerationBudget()
    nav = PathNavigator(stop_prob=0.3)
    for seed in range(100):
        rng = random.Random(seed)
        value = materialize(Recipe(h.descriptor(), rng.getrandbits(64), budget.to_dict(), []))
        path, sub_h, sub_v = nav.select(h, value, rng)
        assert values_equal(_get_node(value, path), sub_v)
