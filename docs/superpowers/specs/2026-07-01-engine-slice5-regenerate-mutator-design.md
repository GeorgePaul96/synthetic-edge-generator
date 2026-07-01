# Design Spec — synthedge Engine, Slice 5 (Regenerate Mutator)

- **Date:** 2026-07-01
- **Status:** Approved design (pre-implementation)
- **Builds on:** Slices 1–4 frozen contracts (mutators emit a `LineageOp`; live ≡ replay).
- **Scope:** Make generated leaf-composite values (model/dataclass/set/tuple/enum) actually reach the
  function under test during fuzzing.

---

## 1. Problem

The fuzz loop mutates every input before executing it (base seeds are never run directly). For a
**leaf-composite** value — a Pydantic model, dataclass, `set`, `tuple`, or `Enum` member — the only
applicable mutator is `ScalarMutator`, which replaces the whole value with a scalar from a fixed pool.

Measured on an `Account` (Pydantic) parameter over 200 mutations: the function received
`int/float/str/bool/None` — **zero `Account` instances**. All field-level generation built in Slices
3–4 is discarded at the boundary.

## 2. Goal

Add a mutator that replaces a value with a **fresh, handler-generated instance of the same type**, so
adversarial models/dataclasses/sets/tuples/enums (with varied edge-case fields) reach the code under
test — while preserving determinism and the single live≡replay code path.

### Non-goals

- Descending into composite *fields* (mutating one model field). That needs new path semantics and
  immutability/hashing handling — deferred.
- Any change to the navigator, path model, recipe, or replay logic.

## 3. Design

New mutator `RegenerateMutator` in `edge_case_engine/mutators/regenerate.py`:

```python
class RegenerateMutator(Mutator):
    def can_mutate(self, handler, value) -> bool:
        return not isinstance(value, (list, dict))   # leaves; list/dict stay structural
    def mutate(self, handler, value, rng, budget, path):
        fresh = handler.generate(rng, budget.child())
        return LineageOp("scalar.replace", list(path), {"value": encode(fresh)})
```

- It emits a **`scalar.replace`** `LineageOp` carrying the encoded fresh value, so `_compute_op`
  already handles it — **no replay change, no new op type**. Live mutation (`apply_lineage_op(base,
  op)`) equals replay by construction (invariant M1′).
- Registry default becomes `[ListMutator(), DictMutator(), RegenerateMutator(), ScalarMutator()]`.
  `choose()` picks uniformly among applicable mutators, so a leaf value is ~50% regenerated (fresh
  same-type adversarial instance) and ~50% scalar-replaced (type confusion). Both are useful.
- `handler.generate` is seeded → determinism preserved. `encode(fresh)` is supported for every handler
  output (scalars, set/tuple, enum, dataclass, pydantic).

## 4. Invariants

- **M1′ (single application path):** unchanged — regenerate emits `scalar.replace`, applied by the same
  `apply_lineage_op`.
- **P-regen (replay):** a recipe ending in a regenerate op replays to the same fresh instance (incl.
  `nan` fields), because the encoded value is stored in the op.
- **Determinism:** the mutated value is a pure function of `(rng, budget)`.

## 5. Definition of Done — Architecture Gate v5

- ✓ **Composites reach the code:** over a seeded run of `mutate_step` on an `Account` (and a dataclass)
  parameter, the mutated value is an instance of the model/dataclass a **non-zero** fraction of the
  time (was 0).
- ✓ **Live ≡ replay:** for regenerate ops over many seeds, `apply_lineage_op(deepcopy(base), op)`
  equals `materialize(Recipe(..., lineage=[op]))` (`values_equal`).
- ✓ **Type-preserving:** `RegenerateMutator.mutate` on a value of type T yields an op whose applied
  result is also type T (for scalars, set, tuple, enum, dataclass, model).
- ✓ All 140 existing tests stay green; lists/dicts remain structurally mutated.

## 6. Migration & file plan

New:
- `edge_case_engine/mutators/regenerate.py` — `RegenerateMutator`.
- `tests/test_regenerate_mutator.py` — unit + gate-v5 cases (pydantic parts `importorskip`).

Modified:
- `edge_case_engine/mutators/registry.py` — add `RegenerateMutator` to the default list.

Reused unchanged: recipe/apply_lineage_op, navigator, engine `mutate_step`, codec, all handlers.

## 7. Risks

- **R-1 Overlap with ScalarMutator.** Intentional: both apply to leaves; `choose()` mixes them. No
  correctness issue.
- **R-2 Budget exhaustion.** `handler.generate(rng, budget.child())` respects the size accountant;
  composites emit minimal terminals when exhausted, as elsewhere.
- **R-3 Encodability.** Every handler output is codec-encodable (verified in Slices 1–4); a fresh
  instance is therefore always storable in the op.

## 8. Summary

A ~30-line mutator plus one registry line closes the gap between synthedge's rich type generation and
what the code under test actually receives: fresh, adversarial, same-type composite instances now flow
into targets, with zero changes to replay, navigator, or recipe machinery.
