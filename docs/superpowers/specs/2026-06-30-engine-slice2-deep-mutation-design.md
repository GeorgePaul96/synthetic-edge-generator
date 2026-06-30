# Design Spec — synthedge Engine, Slice 2 (Deep Mutation + Generics)

- **Date:** 2026-06-30
- **Status:** Approved design (pre-implementation)
- **Builds on:** `docs/superpowers/specs/2026-06-29-engine-rewrite-slice1-design.md` (Slice 1 frozen contracts)
- **Scope:** Make mutation exploit the structured inputs Slice 1 can already generate, and round out the structural type set.

---

## 1. Purpose & goals

Slice 1 can *generate* `list[dict[str, int]]` and replay it, but the fuzz loop only mutates
**parameter 0, at the root** — the structure-aware mutators never reach inside a value or touch other
parameters. Slice 2 makes mutation:

1. **Nested** — mutate a sub-node at any depth inside a value (`RecursiveMutator` capability).
2. **Multi-parameter** — mutate a randomly chosen parameter each iteration, not just `param[0]`.
3. **Single-path** — live mutation and replay share one code path, so they cannot diverge.

It also finishes the **structural** type set: `set`, `tuple` (fixed and variadic), and `Literal`.

### Non-goals (Slice 2)

- **Enum, dataclass, Pydantic** — deferred to the next slice. All three need the same new machinery
  (serialize an instance of a user-declared class by `module:qualname` identity); building it once,
  together, is cleaner than enum-only here. Slice 2 stays purely structural.
- Branch/edge coverage (still line-level).
- Mutating *into* `set`/`tuple` elements (sets are unordered/hash-sensitive; tuples immutable). They
  are **leaf** mutation sites in Slice 2 — mutated as whole nodes, not descended into.

---

## 2. The core decision: mutators emit a `LineageOp`, engine applies it

Slice 1 mutators returned `(new_value, op)`: the live loop trusted `new_value`, replay re-derived from
`op`. With nested mutation that is two code paths that can silently diverge — the exact failure the
corpus integrity check exists to catch.

**Change:** a mutator returns **only** a `LineageOp` (a concrete, encoded effect at a given path). The
engine derives the mutated value by **applying that op** with the same `apply_lineage_op` used in
replay:

```
op = mutator.mutate(sub_handler, sub_value, rng, budget, path)   # returns LineageOp
new_param = apply_lineage_op(deepcopy(base_param), op)           # SAME function replay uses
```

Live mutation ≡ replay, by construction. Invariant **M1** (Slice 1) is strengthened: there is exactly
one mutation-application implementation.

---

## 3. Generalized paths

`LineageOp.path` (always `[]` in Slice 1) becomes a list of typed segments addressing a sub-node:

```python
# segment forms (JSON-safe):
["list", i]                 # descend into list index i
["dict", <encoded_key>]     # descend into dict at key (codec-encoded, keys may be non-str)
```

Navigation/application helpers (in `edge_case_engine/recipe.py`):

```python
def _get_node(root, path):
    """Return the live sub-node at path (traverses list/dict only)."""

def _set_node(root, path, new_node):
    """Set the sub-node at path in place via its parent; path == [] replaces root.
    Returns the (possibly new) root."""

def _compute_op(op, old_node):
    """Pure: old node -> new node for one op (scalar.replace / list.* / dict.*)."""

def apply_lineage_op(root, op):
    target = _get_node(root, op.path)
    return _set_node(root, op.path, _compute_op(op, target))
```

`_get_node`/`_set_node` only ever traverse **list** and **dict** nodes (the only descendable
containers — see §5), so every parent on a path is mutable; no immutable-rebuild is needed.

---

## 4. PathNavigator

New module `edge_case_engine/navigator.py`:

```python
class PathNavigator:
    def __init__(self, stop_prob: float = 0.5):
        self.stop_prob = stop_prob

    def select(self, handler, value, rng) -> tuple[list, "Handler", object]:
        """Walk down (handler, value) together, returning (path, sub_handler, sub_value).
        At each descendable node: stop with probability stop_prob, else descend into a
        random child, appending a segment. Optional/Union are unwrapped transparently
        (no segment added)."""
```

- **Unwrapping:** a helper `effective_handler(handler, value)` collapses `OptionalHandler` (→ `inner`
  when `value is not None`) and `UnionHandler` (→ the option whose kind matches `value`) so the
  handler always matches the concrete runtime value before a descent decision.
- **Descendable nodes:** `ListHandler` with a non-empty list (→ random index) and `DictHandler` with a
  non-empty dict (→ random key). Everything else (scalars, `Literal`, `set`, `tuple`, empty/`None`,
  stopped containers) is a **leaf** site.
- Determinism: `select` consumes only the passed `rng`.

---

## 5. Mutation flow (engine + CLI)

Per fuzz iteration:

1. Pick a random parameter index `pi` (uniform over the target's parameters).
2. `path, h_sub, v_sub = navigator.select(handlers[pi], base_input[pi], rng)`.
3. `mutator = registry.choose(h_sub, v_sub, rng)` (Scalar/List/Dict as in Slice 1; `ScalarMutator`
   handles scalar/`Literal`/`set`/`tuple` leaves by whole-node replacement).
4. `op = mutator.mutate(h_sub, v_sub, rng, budget, path)` — `op.path == path`.
5. `new_param = apply_lineage_op(deepcopy(base_input[pi]), op)`.
6. Rebuild the input tuple with `new_param` at `pi`; append `op` to **parameter `pi`'s** recipe
   lineage (a per-parameter copy).
7. Execute; on new coverage push to the pool and persist; on crash record (as Slice 1).

No new mutator classes: `ListMutator`/`DictMutator` now also fire at nested paths because the navigator
hands them a nested `(handler, value)` site; `ScalarMutator` covers all leaves.

---

## 6. New handlers (structural)

| Handler | Type forms | `generate` | `descriptor` | Codec |
|---|---|---|---|---|
| `SetHandler(elem)` | `set[X]` | set of ≤`max_list_length` unique `elem` values (budget-charged) | `{"k":"set","elem":…}` | `set` already supported |
| `TupleHandler(elems, variadic)` | `tuple[A,B]` (fixed) / `tuple[A, ...]` (variadic) | fixed: one of each elem; variadic: 0..N of one elem type | `{"k":"tuple","elems":[…],"variadic":bool}` | `tuple` already supported |
| `LiteralHandler(values)` | `Literal[a,b,…]` | `rng.choice(values)` | `{"k":"literal","values":[encoded…]}` | values are primitives |

Resolver additions (`typing.get_origin`/`get_args`):
- `set` → `SetHandler(resolve(arg))`
- `tuple` → variadic if `args[-1] is Ellipsis` (`TupleHandler([resolve(args[0])], variadic=True)`),
  else fixed (`TupleHandler([resolve(a) for a in args], variadic=False)`)
- `typing.Literal` → `LiteralHandler(list(args))`

`from_descriptor` gains `set`/`tuple`/`literal` cases (literal values decoded via the codec).
`edge_cases()`: `set` → `set()`, `{first elem edge}`; `tuple` (fixed) → tuple of each elem's first
edge; `tuple` (variadic) → `()`, `(edge,)`; `literal` → each value in turn.

> `TupleHandler` is a **leaf** for nested descent (§4); generation builds it, `ScalarMutator` mutates
> it as a whole node. Same for `SetHandler`.

---

## 7. Invariants (additions to Slice 1 §6)

- **M1′ (single application path):** the value produced live equals `apply_lineage_op(base, op)` for
  the emitted op — there is no second mutation implementation.
- **P3 (nested replay):** for any recipe with non-empty-path lineage, `materialize(recipe)` reproduces
  the exact mutated value; corpus integrity holds at depth.
- **N1 (navigator soundness):** every `(path, sub_handler, sub_value)` returned by `select` satisfies
  `_get_node(value, path) == sub_value` and `sub_handler` matches `sub_value`'s kind.
- **D1 (no aliasing):** live mutation never mutates a pooled value in place (operates on a `deepcopy`).

---

## 8. Definition of Done — Architecture Gate v2

Extends Slice 1's gate; new fixture includes `set[int]`, `tuple[int, str]`, `tuple[int, ...]`,
`Literal["a","b"]`, and a nested `list[dict[str, list[int]]]`:

- ✓ **Nested mutation replay** — mutate inside `list[dict[str, int]]`; the resulting recipe replays to
  the identical value (P3).
- ✓ **Live ≡ replay** — for a sampled set of ops, `loop_value == apply_lineage_op(base, op)` (M1′).
- ✓ **Multi-parameter coverage** — over a seeded run on a 3-parameter target, every index is mutated
  at least once.
- ✓ **Navigator soundness** — N1 holds for many random selects on nested fixtures.
- ✓ **Generics** — `set`/`tuple` (fixed+variadic)/`Literal` generate and replay round-trip; resolver
  maps each; `fallback_rate` stays `0` on the fixture.
- ✓ **No exponential blow-up** — aggregate node count bounded on deep nested types (Slice 1 B1).
- ✓ All Slice 1 tests stay green.

---

## 9. Migration & file plan

New:
- `edge_case_engine/navigator.py` — `PathNavigator`, `effective_handler`.
- `type_handlers/set_handler.py`, `tuple_handler.py`, `literal_handler.py`.

Modified:
- `edge_case_engine/recipe.py` — generalized `_get_node`/`_set_node`/`_compute_op`; `apply_lineage_op`
  supports non-empty paths.
- `edge_case_engine/mutators/{scalar,collection}.py` — `mutate(...)` returns `LineageOp` only (drop the
  `new_value` element); `ScalarMutator.can_mutate` unchanged (still all non-list/dict leaves).
- `edge_case_engine/mutators/base.py` — docstring/contract update to the op-only return.
- `synthedge/cli.py` (`run_fuzzer`) and `edge_case_engine/engine.py` — multi-parameter mutation via the
  navigator; per-parameter lineage append.
- `type_handlers/resolver.py` — `set`/`tuple`/`Literal` resolution + `from_descriptor` cases.

Tests updated/added:
- `tests/test_mutators.py` — adapt to op-only return.
- New: `tests/test_navigator.py`, `tests/test_generics_handlers.py`, `tests/test_nested_mutation.py`,
  and Architecture-Gate-v2 cases in `tests/test_architecture_gate.py`.

Reused unchanged: budget, rng, codec (set/tuple already covered), discovery, contracts, executor,
path_tracker, scheduler, deduplicator, minimizer, corpus.

---

## 10. Risks & open questions

- **R-1 Lineage path validity under structural change.** A later op's path is computed against the
  value state *after* earlier ops. Replay reconstructs the same intermediate states in order, so paths
  stay valid. Tests must cover multi-op lineages that delete/insert before a deeper op.
- **R-2 Union runtime matching.** `effective_handler` must match a value to the right `UnionHandler`
  option by kind (incl. `bool` vs `int`). Use type-strict matching mirroring the codec's `values_equal`
  rules.
- **R-3 Empty-container leaves.** Navigator must treat empty list/dict as leaves (no index/key to
  descend); `ListMutator`/`DictMutator` already handle empty via their fallback ops.
- **R-4 Mutator return-type change is breaking.** All call sites and `test_mutators.py` update in the
  same plan; no external consumers exist.

---

## 11. Summary

Slice 2 turns the structured-generation engine into a structured-*mutation* engine: a `PathNavigator`
selects a sub-node at any depth across any parameter, mutators emit a single `LineageOp`, and the
engine applies it through the very function replay uses — guaranteeing live ≡ replay at depth. It also
completes the structural type set (`set`, `tuple` fixed/variadic, `Literal`). Enum and user-defined
classes are deferred to the next slice, where class-identity serialization is built once.
