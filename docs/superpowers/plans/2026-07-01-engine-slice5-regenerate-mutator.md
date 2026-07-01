# Engine Slice 5 (Regenerate Mutator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make generated leaf-composite values (model/dataclass/set/tuple/enum) reach the code under test by adding a mutator that regenerates a fresh same-type instance.

**Architecture:** `RegenerateMutator` emits a `scalar.replace` `LineageOp` carrying a freshly handler-generated, encoded value; registered alongside `ScalarMutator`. No replay/navigator/recipe changes.

**Tech Stack:** Python 3.9+ (stdlib core), Pydantic optional, pytest.

## Global Constraints

- Python **3.9+**, stdlib core; Pydantic optional (tests `importorskip`).
- Mutator returns a `LineageOp`; reuse `scalar.replace` (no new op type, no replay change).
- Determinism preserved; live ≡ replay (M1′).
- Test interpreter: `python3.14 -m pytest`. All 140 existing tests stay green.
- Reference spec: `docs/superpowers/specs/2026-07-01-engine-slice5-regenerate-mutator-design.md`.
- Commit after every task.

---

### Task 1: RegenerateMutator + registry wiring

**Files:**
- Create: `edge_case_engine/mutators/regenerate.py`
- Modify: `edge_case_engine/mutators/registry.py`
- Test: `tests/test_regenerate_mutator.py`

**Interfaces:**
- Consumes: `Mutator`, `LineageOp`, `codec.encode`, a handler's `generate`.
- Produces: `RegenerateMutator` with `can_mutate(handler, value) -> bool` (True for non-list/dict) and
  `mutate(handler, value, rng, budget, path) -> LineageOp` (op `"scalar.replace"`, args `{"value":
  encode(fresh)}`). `MutatorRegistry` default list includes it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_regenerate_mutator.py
import random
from edge_case_engine.budget import GenerationBudget
from edge_case_engine.recipe import LineageOp, apply_lineage_op
from edge_case_engine.codec import values_equal, decode
from edge_case_engine.mutators.regenerate import RegenerateMutator
from edge_case_engine.mutators.registry import MutatorRegistry
from type_handlers.scalars import IntegerHandler
from type_handlers.tuple_handler import TupleHandler
from type_handlers.list_handler import ListHandler


def test_regenerate_produces_same_type_and_is_applyable():
    h = TupleHandler([IntegerHandler(), IntegerHandler()], variadic=False)
    op = RegenerateMutator().mutate(h, (1, 2), random.Random(3), GenerationBudget(), path=[])
    assert isinstance(op, LineageOp) and op.op == "scalar.replace"
    applied = apply_lineage_op((9, 9), op)
    assert isinstance(applied, tuple)                 # type preserved
    assert values_equal(applied, decode(op.args["value"]))


def test_regenerate_skips_list_and_dict():
    m = RegenerateMutator()
    assert m.can_mutate(IntegerHandler(), 5) is True
    assert m.can_mutate(ListHandler(IntegerHandler()), [1]) is False


def test_registry_includes_regenerate():
    kinds = {type(m).__name__ for m in MutatorRegistry()._mutators}
    assert "RegenerateMutator" in kinds
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_regenerate_mutator.py -v`
Expected: FAIL with `ModuleNotFoundError: edge_case_engine.mutators.regenerate`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/mutators/regenerate.py
from edge_case_engine.mutators.base import Mutator
from edge_case_engine.recipe import LineageOp
from edge_case_engine.codec import encode


class RegenerateMutator(Mutator):
    """Replace a leaf value with a fresh, handler-generated instance of the same type.
    Emitted as a scalar.replace op so replay reuses the existing apply path."""

    def can_mutate(self, handler, value) -> bool:
        return not isinstance(value, (list, dict))   # list/dict stay structurally mutated

    def mutate(self, handler, value, rng, budget, path):
        fresh = handler.generate(rng, budget.child())
        return LineageOp(op="scalar.replace", path=list(path), args={"value": encode(fresh)})
```

```python
# edge_case_engine/mutators/registry.py  (replace default list)
from edge_case_engine.mutators.scalar import ScalarMutator
from edge_case_engine.mutators.collection import ListMutator, DictMutator
from edge_case_engine.mutators.regenerate import RegenerateMutator


class MutatorRegistry:
    def __init__(self, mutators=None):
        self._mutators = mutators if mutators is not None else [
            ListMutator(), DictMutator(), RegenerateMutator(), ScalarMutator(),
        ]

    def applicable(self, handler, value):
        return [m for m in self._mutators if m.can_mutate(handler, value)]

    def choose(self, handler, value, rng):
        candidates = self.applicable(handler, value)
        return rng.choice(candidates) if candidates else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_regenerate_mutator.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/mutators/regenerate.py edge_case_engine/mutators/registry.py tests/test_regenerate_mutator.py
git commit -m "feat: add RegenerateMutator so fresh composites reach targets"
```

---

### Task 2: Architecture Gate v5

**Files:**
- Modify: `tests/test_regenerate_mutator.py` (append)
- Test: same file

**Interfaces:**
- Consumes: `EdgeCaseEngine.mutate_step`, resolver, recipe replay.
- Produces: gate assertions — composites now reach the code; live ≡ replay for regenerate ops.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_regenerate_mutator.py  (append)
import copy
from dataclasses import dataclass
from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.recipe import Recipe, materialize
from type_handlers.resolver import TypeResolver


@dataclass
class _P:
    a: int
    b: int


def test_dataclass_instances_reach_the_function():
    engine = EdgeCaseEngine()
    handlers = [TypeResolver.resolve(_P)]
    budget = GenerationBudget()
    master = random.Random(0)
    base_input, base_recipes = engine.generate_seeds(handlers, master, budget, n_random=1)[0]
    received_dc = 0
    for _ in range(200):
        mutated, new_recipes, pi = engine.mutate_step(handlers, base_input, base_recipes, master, budget)
        if isinstance(mutated[0], _P):
            received_dc += 1
    assert received_dc > 0            # was 0 before RegenerateMutator


def test_live_equals_replay_for_regenerate_ops():
    h = TypeResolver.resolve(_P)
    budget = GenerationBudget()
    m = RegenerateMutator()
    for seed in range(100):
        rng = random.Random(seed)
        base_recipe = Recipe(h.descriptor(), rng.getrandbits(64), budget.to_dict(), [])
        base = materialize(base_recipe)
        op = m.mutate(h, base, rng, budget, path=[])
        live = apply_lineage_op(copy.deepcopy(base), op)
        replay = materialize(Recipe(h.descriptor(), base_recipe.seed, budget.to_dict(), [op]))
        assert values_equal(live, replay)
```

- [ ] **Step 2: Run test to verify it fails (or passes if Task 1 complete)**

Run: `python3.14 -m pytest tests/test_regenerate_mutator.py -v`
Expected: PASS once Task 1 is in. If `received_dc > 0` fails, RegenerateMutator is not registered.

- [ ] **Step 3: No new implementation**

Validates the assembled behavior end-to-end.

- [ ] **Step 4: Run the full suite**

Run: `python3.14 -m pytest -q`
Expected: PASS (all 140 prior tests + Slice 5 tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_regenerate_mutator.py
git commit -m "test: gate v5 (composites reach targets, regenerate replay)"
```

---

## Self-Review

**Spec coverage:** §3 RegenerateMutator + registry → Task 1. §4 invariants (M1′, P-regen via
`scalar.replace`) → Tasks 1, 2. §5 DoD (composites reach code, live≡replay, type-preserving) → Task 2.
§6 file plan → Tasks 1–2. ✓

**Placeholder scan:** None. Full code shown for the mutator and registry.

**Type consistency:** `RegenerateMutator.can_mutate/mutate`, `LineageOp("scalar.replace", path, {"value":
encode(...)})`, `MutatorRegistry._mutators` used consistently. ✓

## Notes for the implementer
- Run `python3.14 -m pytest` after each task.
- Do not add a new lineage op — regenerate deliberately reuses `scalar.replace` for zero replay change.
