# Design Spec — synthedge Engine Rewrite, Slice 1

- **Date:** 2026-06-29
- **Status:** Approved design (pre-implementation)
- **Scope:** v0.2 core engine — generation/mutation/corpus rearchitecture
- **Supersedes:** the enumeration-based engine in `edge_case_engine/engine.py`,
  `edge_case_engine/combinatorial.py`, `edge_case_engine/mutation.py`, and the flat
  `type_handlers/registry.py` `_TYPE_MAP`.

---

## 1. Purpose & goals

synthedge today only fuzzes flat scalar parameters (`float/int/str/bool/None`); anything else falls
back to `FloatHandler`. This makes it useless on the majority of real typed Python functions, which
take `list`, `dict`, `Optional`, `Union`, and nested combinations.

This spec defines a **generation-based engine** that:

1. Generates structured inputs from type hints (Slice 1: `Optional`, `Union`, `list`, `dict`, plus the
   existing scalars).
2. Mutates them with **structure-aware, interchangeable** mutation strategies.
3. Runs deterministically under a seed.
4. Persists a **replayable recipe** (intent, not just the materialized value) in a versioned corpus.

Slice 1 is intentionally narrow: it proves the architecture on the smallest type set that exercises
every hard mechanic (recursion, composition, budgeting, replay). Once proven, `set`/`tuple`/`Literal`/
`Enum`/`TypedDict`/dataclass/Pydantic are incremental additions.

### Non-goals (Slice 1)

- `set`, `tuple`, `Literal`, `Enum`, `TypedDict`, dataclasses, Pydantic.
- Branch/edge coverage (stays line-level for now).
- HTML reports, CLI polish, CI/GitHub Action.
- Characterization assertions (capturing return values for `assert ==` tests). The corpus envelope
  reserves room for it (`artifacts.output`) but Slice 1 does not populate or use it.

---

## 2. Motivation: why this is an engine rewrite, not a handler addition

Three assumptions are baked into the current engine and all break on structured types:

| Current assumption | Why structured types break it | Replacement |
|---|---|---|
| Handlers return a **finite list** of edge cases | `list[dict[str,int]]` has no finite enumerable list | Handlers **sample** one value from a seeded RNG; `edge_cases()` is a **lazy iterator** |
| Engine takes `itertools.product` across param lists | Product of unbounded structured values explodes | Bounded edge-case sampling + N random samples per param |
| Mutation replaces a whole argument with a value from a 7-item pool | Replacing a `dict` with `inf` probes nothing | **Structure-aware mutators** that recurse into the value |

---

## 3. Architecture overview

```
type hints ──► TypeResolver ──► Handler tree
                                     │
                  ┌──────────────────┴───────────────────┐
                  ▼                                       ▼
            generate(rng, budget)                   edge_cases()  (lazy)
                  │                                       │
                  └───────────────► base input ◄──────────┘
                                       │
                  (fuzz loop)          ▼
            MutatorRegistry ──► Mutator.mutate(handler, value, rng, budget)
                                       │
                                       ▼
                              mutated input + lineage op
                                       │
                                       ▼
                        FunctionExecutor.execute  ─► artifacts (exception, coverage, output*)
                                       │
                                       ▼
                              CorpusManager ─► versioned envelope { recipe, input, artifacts }
                                       │
                                       ▼
                              replay: recipe ──► identical input  (integrity-checked)
```

Components and their single responsibilities:

- **`TypeResolver`** — turns a `typing` annotation into a **handler tree**. Knows nothing about RNG.
- **`Handler` tree** — generates and describes values for one type node. Composites hold child handlers.
- **`GenerationBudget`** — shared resource limits + a size accountant. Passed into every `generate`.
- **RNG derivation** — deterministic child-RNG scheme so traversal order fully determines a value.
- **`Mutator` hierarchy + `MutatorRegistry`** — interchangeable mutation strategies operating on a
  `(handler, value)` pair.
- **`Recipe`** — replayable record: `type_sig + seed + budget + ordered mutation lineage`.
- **`CorpusManager`** — versioned, serializable persistence; replay + integrity check.

---

## 4. Core interfaces

These are the frozen contracts. Signatures are normative.

### 4.1 Handler protocol

```python
# type_handlers/base.py
import random
from typing import Any, Iterator

class Handler:
    """Generates and describes values for ONE type node. No mutation logic here."""

    def generate(self, rng: random.Random, budget: "GenerationBudget") -> Any:
        """Sample exactly one value. MUST be a pure function of (rng state, budget)."""
        raise NotImplementedError

    def edge_cases(self) -> Iterator[Any]:
        """Yield boundary/extreme values, HIGHEST-VALUE FIRST, lazily.
        Consumers take the first K and stop, so order matters and the iterator
        may be effectively unbounded for composites."""
        raise NotImplementedError

    def type_sig(self) -> str:
        """Stable string signature of this node, e.g. 'list[dict[str, int]]'.
        Used as the recipe key and for resolver round-tripping."""
        raise NotImplementedError
```

Composite handlers additionally hold their child handlers as attributes (e.g.
`ListHandler.elem: Handler`, `DictHandler.key: Handler`, `DictHandler.val: Handler`,
`UnionHandler.options: list[Handler]`, `OptionalHandler.inner: Handler`). The mutator layer reads
these to do type-aware sub-generation.

### 4.2 Type resolver

```python
# type_handlers/resolver.py
class TypeResolver:
    @classmethod
    def resolve(cls, annotation, *, strict: bool = False) -> Handler:
        """Map a typing annotation to a Handler tree using typing.get_origin/get_args.
        Slice 1 mapping:
          float/int/str/bool/None  -> scalar handlers
          list[X]                  -> ListHandler(resolve(X))
          dict[K, V]               -> DictHandler(resolve(K), resolve(V))
          Optional[X] / X | None   -> OptionalHandler(resolve(X))
          Union[A, B, ...]         -> UnionHandler([resolve(A), resolve(B), ...])
          unknown / unannotated    -> FloatHandler (fallback);
                                      records a fallback event; raises if strict=True
        """
```

The resolver also exposes `fallback_rate()` over a run so the Definition-of-Done gate
(`generic fallback < 10%`) is measurable.

### 4.3 Generation budget

```python
# edge_case_engine/budget.py
from dataclasses import dataclass

@dataclass
class GenerationBudget:
    max_depth: int = 4               # recursion depth for nested containers
    max_list_length: int = 8
    max_dict_keys: int = 8
    max_string_length: int = 64
    probability_none: float = 0.1    # Optional / nullable draw
    union_weights: tuple = ()        # optional per-option weights for UnionHandler
    max_total_nodes: int = 256       # SIZE ACCOUNTANT: hard cap on aggregate node count

    def child(self) -> "GenerationBudget":
        """Return a budget with depth decremented for one level of recursion."""

    def spend(self, n: int = 1) -> bool:
        """Charge the shared node accountant. Returns False when exhausted, at which
        point composites MUST emit a minimal terminal (empty container / None)."""
```

The accountant is **shared across the whole input** (threaded by reference), so deeply nested types
cannot be "small at every level yet huge in aggregate."

### 4.4 Deterministic RNG derivation

```python
# edge_case_engine/rng.py
import random

def derive_child(rng: random.Random) -> random.Random:
    """Deterministically derive a child RNG by drawing a fresh 64-bit seed from the
    parent. Because traversal order is fixed (see invariants), the master seed alone
    determines every value. Composites call this once per child, in traversal order."""
    return random.Random(rng.getrandbits(64))
```

Mutation does **not** rely on RNG replay: mutation lineage stores concrete *effects* (see §4.6), so
replay is RNG-independent for the mutation layer and seed-determined for base generation.

### 4.5 Mutator hierarchy

```python
# edge_case_engine/mutators/base.py
class Mutator:
    """A mutation STRATEGY. Operates on a (handler, value) pair so it can borrow the
    handler tree for type-aware sub-generation, while remaining swappable."""

    def can_mutate(self, handler: Handler, value) -> bool: ...

    def mutate(self, handler: Handler, value, rng: random.Random,
               budget: "GenerationBudget") -> tuple[Any, "LineageOp"]:
        """Return (new_value, lineage_op). lineage_op records the concrete effect
        (path + encoded literal args) so it can be replayed without RNG."""
```

Slice 1 concrete mutators:

- `ScalarMutator` — today's behavior: replace with a value from the scalar pool / an `edge_cases()`
  draw of the node's handler.
- `ListMutator` — `insert` (new element via `handler.elem.generate`), `delete`, `duplicate`,
  `reverse`, `grow`, `empty`.
- `DictMutator` — `drop_key`, `add_key` (typed via `handler.key`/`handler.val`), `corrupt_value_type`,
  `corrupt_key_type`.
- `RecursiveMutator` — descend one level into a container and apply a child mutator to a child node.

`MutatorRegistry` selects an applicable mutator per node-kind. Strategies are interchangeable: adding
coverage-guided / grammar / dictionary / AI mutators later means adding a `Mutator` subclass, with
**zero handler changes**.

### 4.6 Recipe & lineage

```python
# edge_case_engine/recipe.py
@dataclass
class LineageOp:
    op: str            # e.g. "list.insert", "dict.drop_key", "scalar.replace"
    path: list         # navigation path into the value, e.g. ["[0]", "age"]
    args: dict         # encoded literal effect args (already serialized form)

@dataclass
class Recipe:
    type_sig: str
    seed: int
    budget: dict       # serialized GenerationBudget
    lineage: list      # ordered list[LineageOp]
```

**Replay** = resolve `type_sig` → handler tree → `generate` base with `(seed, budget)` → apply each
`LineageOp` in order. Because lineage stores concrete effects, replay is deterministic regardless of
the RNG used when the mutation was originally discovered.

### 4.7 Corpus envelope & serialization

Envelope (versioned, one JSON object per entry):

```json
{
  "version": 1,
  "seed": 42,
  "recipe": { "type_sig": "...", "seed": 42, "budget": { }, "lineage": [ ] },
  "input": { },
  "artifacts": {
    "output": null,
    "exception": null,
    "coverage": null
  }
}
```

- `recipe` is the **source of truth**. `input` is a **denormalized cache** for readability/fast load.
- On load, the corpus **replays the recipe and asserts the result equals `input`** (integrity check);
  a mismatch is a corruption/version error, not silently ignored.
- `artifacts` is a generic bag — Slice 1 fills `exception`/`coverage`; `output` reserved for future
  characterization mode.

**Tagged serialization** (replaces today's raw `Infinity`/`NaN` JSON) handles non-JSON values
losslessly:

```json
{"$t": "float", "$v": "nan"}      // also "inf", "-inf"
{"$t": "bytes", "$v": "<base64>"}
{"$t": "set",   "$v": [ ... ]}
{"$t": "tuple", "$v": [ ... ]}
```

Plain JSON scalars/containers pass through untagged. A single `codec.encode/decode` pair owns this and
is the only place that knows the tag scheme.

Storage layout:

```
.synthedge/
  corpus/        # interesting inputs (envelopes) — persistent across runs
  crashes/       # deduplicated crash envelopes
  metadata.json  # version, seed history, run stats
```

---

## 5. Data flow

1. **Resolve** — for each target, `typing.get_type_hints` → `TypeResolver.resolve` per parameter →
   a tuple of handler trees.
2. **Seed corpus** — for each parameter, draw a bounded prefix of `edge_cases()` plus N random
   `generate(rng, budget)` samples; combine across parameters (bounded, not full product); dedupe;
   record each as a `Recipe` with empty lineage. Load any persisted corpus from `.synthedge/`.
3. **Fuzz loop** — `PowerScheduler.choose_next_seed` → pick a `Mutator` from the registry →
   `mutate(handler, value, rng, budget)` → append the returned `LineageOp` to the recipe →
   `FunctionExecutor.execute`.
4. **Learn/record** — new coverage → keep as interesting (persist envelope); crash → record crash
   envelope. Artifacts captured from execution.
5. **Persist** — envelopes written under `.synthedge/`. `metadata.json` updated.
6. **Replay** (on demand, and at load for integrity) — recipe → identical input.

The existing `executor.py` / `path_tracker.py` / `scheduler.py` / `deduplicator.py` / `minimizer.py`
are reused; `executor.execute` is extended to populate `artifacts`.

---

## 6. Invariants

**Handler invariants**
- H1 **Deterministic:** `generate(rng, budget)` is a pure function of RNG state + budget.
- H2 **Terminating:** respects `max_depth` and the shared accountant; at exhaustion emits a minimal
  terminal. Never recurses unbounded.
- H3 **Lazy edge cases:** `edge_cases()` yields highest-value-first and may be unbounded; consumers
  take a finite prefix.
- H4 **Stable signature:** `type_sig()` is stable and round-trips through the resolver.
- H5 **Serializable:** every value `generate` can produce is encodable by the codec.

**RNG / traversal invariants**
- R1 **Fixed traversal order:** composites visit children in a fixed, documented order.
- R2 **Child derivation:** child RNGs are obtained only via `derive_child`, in traversal order, so the
  master seed alone reproduces the base value.

**Mutator invariants**
- M1 **Effect-recording:** every mutation returns a `LineageOp` whose `args` are already-encoded
  literals, making replay RNG-independent.
- M2 **Type-preserving where intended:** type-aware ops (insert/add_key) produce values via the
  relevant child handler; type-corruption ops are explicit and named as such.

**Replay invariants**
- P1 **Round-trip:** `replay(recipe) == input` for every persisted envelope.
- P2 **Integrity-checked load:** mismatch raises rather than loading silently.

**Budget invariant**
- B1 **Aggregate bound:** total generated node count ≤ `max_total_nodes` regardless of nesting.

---

## 7. Slice 1 handler set

| Handler | Type | `generate` sketch | Key `edge_cases()` (first few) |
|---|---|---|---|
| `FloatHandler` | `float` | sampled float incl. specials | `0.0, -0.0, inf, -inf, nan, max, min` |
| `IntegerHandler` | `int` | sampled int across magnitudes | `0, 1, -1, maxsize, -maxsize-1, 2**63` |
| `StringHandler` | `str` | sampled str ≤ budget len | `"", " ", "\0", unicode, injection, long` |
| `BoolHandler` | `bool` | `rng.choice([True,False])` | `True, False` |
| `NoneHandler` | `None` | `None` | `None` |
| `OptionalHandler` | `Optional[X]` | `None` w.p. `probability_none` else `inner.generate` | `None`, then `inner.edge_cases()` |
| `UnionHandler` | `Union[...]` | weighted choice of an option, then `.generate` | round-robin first edge of each option |
| `ListHandler` | `list[X]` | length≤budget; elems via `elem.generate` | `[]`, `[edge]`, `[edge, edge]` |
| `DictHandler` | `dict[K,V]` | n≤budget pairs via `key/val.generate` | `{}`, `{edge_k: edge_v}` |

Composites call `budget.spend()` per node and `budget.child()` when recursing.

---

## 8. Testing strategy

- **Per-handler unit tests:** determinism (H1: same seed → same value), budget adherence (H2/B1),
  `edge_cases()` ordering + laziness (H3), signature round-trip (H4).
- **Resolver tests:** annotation → expected handler tree for every Slice 1 form, including
  `Optional[Union[...]]` and `list[dict[str,int]]`; fallback + `strict` behavior; `fallback_rate`.
- **Mutator tests:** each op produces the intended structural change and a replayable `LineageOp`.
- **Codec tests:** round-trip for `nan/inf/-inf/bytes/set/tuple` and nested containers.
- **End-to-end replay tests:** generate → mutate → serialize → load → replay → identical input
  (P1/P2), across many seeds.
- **Architecture-gate fixture** (see §9): ~8 real typed functions, asserted against the DoD.
- Tests live in `tests/`, run with `python -m pytest` (Python 3.9+).

---

## 9. Definition of Done — Architecture Gate

Slice 1 is complete only when, on a fixture including
`process(users: list[dict[str, int]], role: Optional[str], age: Union[int, None])`:

- ✓ **Deterministic generation** — same seed reproduces identical base inputs.
- ✓ **Deterministic mutation** — same seed + lineage reproduces identical mutated inputs.
- ✓ **Corpus replay** — every persisted recipe replays to its cached `input`.
- ✓ **Crash replay** — a stored crash recipe re-triggers the same exception signature.
- ✓ **Nested recursion** — `list[dict[...]]` and `Optional[Union[...]]` generate correctly.
- ✓ **Mutation coverage** — list and dict structural mutators all exercised by tests.
- ✓ **No exponential blow-up** — aggregate node count ≤ `max_total_nodes` on adversarial nested types.
- ✓ **Generic fallback < 10%** — measured `fallback_rate` over the fixture.

---

## 10. Migration & file plan

New:
- `type_handlers/base.py` (Handler), `type_handlers/resolver.py` (TypeResolver),
  `type_handlers/list_handler.py`, `dict_handler.py`, `optional_handler.py`, `union_handler.py`.
- `edge_case_engine/budget.py`, `edge_case_engine/rng.py`, `edge_case_engine/recipe.py`,
  `edge_case_engine/codec.py`, `edge_case_engine/mutators/` (base + scalar/list/dict/recursive).

Rewritten:
- `type_handlers/registry.py` → thin shim delegating to `TypeResolver` (kept for back-compat import).
- existing scalar handlers → new `Handler` interface (their current lists become `edge_cases()`).
- `edge_case_engine/engine.py` → sampling-based generation; `combinatorial.py` retired or folded in.
- `edge_case_engine/mutation.py` → delegates to `MutatorRegistry` (legacy `mutation_engine.py`
  remains dead and is a candidate for deletion).
- `edge_case_engine/corpus.py` → versioned envelope + `.synthedge/` layout + replay/integrity.

Reused as-is (minor edits): `executor.py` (populate artifacts), `path_tracker.py`, `scheduler.py`,
`discovery.py`, `contracts.py`, `deduplicator.py`, `minimizer.py`.

CLI: add `--seed`; default to a random seed that is recorded in `metadata.json` and printed.

---

## 11. Risks & open questions

- **R-1 Determinism vs. `dict`/`set` iteration order.** Generation must not depend on hash-randomized
  iteration; handlers build containers in a fixed, sorted-by-construction order. Codec sorts keys.
- **R-2 Mutation lineage vs. minimization.** `InputMinimizer` currently rewrites inputs directly; it
  must produce lineage ops (or be wrapped) so minimized inputs remain replayable. Confirm during plan.
- **R-3 Cross-run corpus + schema evolution.** `version` field + integrity check guard this; a version
  bump must include a migration or an explicit "discard old corpus" path.
- **R-4 Bounded combination across parameters.** The seed step must cap the cross-parameter combination
  (no full product) — exact bound to be set in the implementation plan.

---

## 12. Summary

Slice 1 replaces the enumeration engine with a **generation-based engine**: resolver-built handler
trees that **sample** (not enumerate), a **separate, interchangeable mutator hierarchy** operating on
`(handler, value)` pairs, a shared **GenerationBudget** with a size accountant, deterministic seeded
RNG, and a **versioned corpus that stores replayable recipes** (intent) with an integrity-checked
denormalized cache and a generic `artifacts` bag. Success is the §9 Architecture Gate on real typed
functions. Everything else in the v0.2–v1.0 roadmap builds on these frozen contracts.
