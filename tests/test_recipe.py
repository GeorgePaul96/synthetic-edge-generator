from typing import List, Dict

from edge_case_engine.budget import GenerationBudget
from edge_case_engine.recipe import (
    Recipe, LineageOp, materialize, apply_lineage_op,
)
from edge_case_engine.codec import encode, values_equal
from type_handlers.resolver import TypeResolver


def test_recipe_materialize_is_deterministic():
    h = TypeResolver.resolve(List[Dict[str, int]])
    budget = GenerationBudget().to_dict()
    r = Recipe(descriptor=h.descriptor(), seed=1234, budget=budget, lineage=[])
    v1 = materialize(r)
    v2 = materialize(r)
    assert values_equal(v1, v2)


def test_recipe_dict_roundtrip():
    r = Recipe(descriptor={"k": "int"}, seed=1, budget=GenerationBudget().to_dict(), lineage=[])
    r2 = Recipe.from_dict(r.to_dict())
    assert r2.seed == 1 and r2.descriptor == {"k": "int"}


def test_apply_scalar_replace():
    out = apply_lineage_op(5, LineageOp("scalar.replace", [], {"value": encode(None)}))
    assert out is None


def test_full_materialize_applies_lineage_in_order():
    r = Recipe(descriptor={"k": "list", "elem": {"k": "int"}}, seed=1,
               budget=GenerationBudget().to_dict(),
               lineage=[LineageOp("list.empty", [], {}),
                        LineageOp("list.insert", [], {"index": 0, "value": encode(99)})])
    assert values_equal(materialize(r), [99])
