# Engine Rewrite (Slice 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace synthedge's enumeration-based engine with a generation-based engine that fuzzes `Optional`, `Union`, `list`, and `dict` (plus existing scalars) deterministically and stores replayable recipes.

**Architecture:** A `TypeResolver` turns type hints into a tree of composable `Handler`s that *sample* values from a seeded `Random` under a shared `GenerationBudget`. A separate, interchangeable `Mutator` hierarchy mutates `(handler, value)` pairs and records concrete `LineageOp`s. A versioned `CorpusManager` persists `{recipe, input, artifacts}` envelopes; `recipe` (seed + budget + lineage) is the replayable source of truth, integrity-checked against the cached `input`.

**Tech Stack:** Python 3.9+ (stdlib only), pytest. No new runtime dependencies.

## Global Constraints

- Python **3.9+** (use `typing.get_origin`/`get_args`; do not require 3.10+ syntax in library code).
- **Stdlib only** for the engine core — no new runtime dependencies.
- All generation/mutation is **deterministic given a seed** (spec invariants H1, R1, R2, M1, P1, P2).
- Handlers **sample** (`generate`) and **lazily yield** (`edge_cases`); never materialize unbounded lists.
- Composites charge the **shared size accountant** (`budget.spend()`) and recurse via `budget.child()`.
- Recipe is source of truth; `input` is a denormalized cache; load **must** integrity-check via replay.
- Reference spec: `docs/superpowers/specs/2026-06-29-engine-rewrite-slice1-design.md`.
- Commit after every task. Run `python -m pytest` (3.9+) for tests.

> **Note on `nan` equality:** `float('nan') != float('nan')`. All equality checks in tests and the
> integrity check use `codec.values_equal`, not `==`.

> **Design concretization (vs spec §4.6):** The spec says `type_sig` round-trips through the resolver.
> To avoid a string parser, the recipe stores a structured **`descriptor`** (nested dict) that the
> resolver rebuilds via `from_descriptor`; `type_sig()` is the human-readable rendering of that
> descriptor. This satisfies invariant H4 without parsing strings.

---

## File Structure

New files:
- `edge_case_engine/budget.py` — `GenerationBudget`
- `edge_case_engine/rng.py` — `derive_child`
- `edge_case_engine/codec.py` — `encode`, `decode`, `values_equal`
- `type_handlers/base.py` — `Handler` ABC
- `type_handlers/scalars.py` — `FloatHandler`, `IntegerHandler`, `StringHandler`, `BoolHandler`, `NoneHandler`
- `type_handlers/list_handler.py`, `dict_handler.py`, `optional_handler.py`, `union_handler.py`
- `type_handlers/resolver.py` — `TypeResolver`
- `edge_case_engine/recipe.py` — `LineageOp`, `Recipe`, `materialize`, `replay`
- `edge_case_engine/mutators/__init__.py`, `base.py`, `scalar.py`, `collection.py`, `recursive.py`, `registry.py`
- `tests/test_budget.py`, `test_rng.py`, `test_codec.py`, `test_scalar_handlers.py`,
  `test_composite_handlers.py`, `test_resolver.py`, `test_recipe.py`, `test_mutators.py`,
  `test_engine_generation.py`, `test_corpus_v2.py`, `test_architecture_gate.py`

Modified files:
- `edge_case_engine/engine.py` — sampling-based `generate`
- `edge_case_engine/corpus.py` — versioned envelope, `.synthedge/` layout, replay/integrity
- `edge_case_engine/executor.py` — populate `artifacts`
- `synthedge/cli.py` — `--seed`, wire new engine/resolver/mutators/corpus
- `type_handlers/registry.py` — thin shim delegating to `TypeResolver`

---

### Task 1: GenerationBudget

**Files:**
- Create: `edge_case_engine/budget.py`
- Test: `tests/test_budget.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `GenerationBudget(max_depth=4, max_list_length=8, max_dict_keys=8, max_string_length=64, probability_none=0.1, union_weights=(), max_total_nodes=256)` with `.child() -> GenerationBudget`, `.spend(n=1) -> bool`, `.depth_exhausted() -> bool`, `.to_dict() -> dict`, classmethod `from_dict(d) -> GenerationBudget`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_budget.py
from edge_case_engine.budget import GenerationBudget

def test_child_shares_accountant_and_decrements_depth():
    b = GenerationBudget(max_depth=3, max_total_nodes=5)
    c = b.child()
    assert c.max_depth == 2
    assert b.spend(3) is True
    assert c.spend(2) is True          # shared pool: 5 - 3 - 2 = 0
    assert c.spend(1) is False         # exhausted
    assert b.spend(1) is False

def test_depth_exhausted_and_roundtrip():
    b = GenerationBudget(max_depth=0)
    assert b.depth_exhausted() is True
    assert GenerationBudget.from_dict(b.to_dict()).max_string_length == b.max_string_length
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_budget.py -v`
Expected: FAIL with `ModuleNotFoundError: edge_case_engine.budget`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/budget.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_budget.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/budget.py tests/test_budget.py
git commit -m "feat: add GenerationBudget with shared size accountant"
```

---

### Task 2: Deterministic RNG derivation

**Files:**
- Create: `edge_case_engine/rng.py`
- Test: `tests/test_rng.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `derive_child(rng: random.Random) -> random.Random`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rng.py
import random
from edge_case_engine.rng import derive_child

def test_child_is_deterministic_from_parent_seed():
    a = derive_child(random.Random(7)).random()
    b = derive_child(random.Random(7)).random()
    assert a == b

def test_sequential_children_differ():
    parent = random.Random(7)
    first = derive_child(parent).random()
    second = derive_child(parent).random()
    assert first != second   # parent state advanced between draws
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rng.py -v`
Expected: FAIL with `ModuleNotFoundError: edge_case_engine.rng`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/rng.py
import random

def derive_child(rng: random.Random) -> random.Random:
    """Deterministically derive a child RNG by drawing a 64-bit seed from the parent.
    Because traversal order is fixed, the master seed alone determines every value."""
    return random.Random(rng.getrandbits(64))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_rng.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/rng.py tests/test_rng.py
git commit -m "feat: add deterministic child-RNG derivation"
```

---

### Task 3: Codec (tagged serialization + value equality)

**Files:**
- Create: `edge_case_engine/codec.py`
- Test: `tests/test_codec.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `encode(value) -> json-safe`, `decode(obj) -> value`, `values_equal(a, b) -> bool`.
  Tag scheme: `{"$t": "float"|"bytes"|"tuple"|"set"|"dict", "$v": ...}`. Plain JSON scalars/lists pass through untagged; **all `dict`s are tagged** (to preserve non-string keys), so any bare object in decoded JSON carries `$t`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_codec.py
import math
from edge_case_engine.codec import encode, decode, values_equal

def test_roundtrip_specials_and_containers():
    value = {"a": [float("nan"), float("inf"), -1], 2: (b"x", {1, 2})}
    restored = decode(encode(value))
    assert values_equal(restored, value)
    # spot check nan survived
    assert math.isnan(restored["a"][0])

def test_values_equal_handles_nan():
    assert values_equal(float("nan"), float("nan")) is True
    assert values_equal(1, 1.0) is False   # type-strict
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_codec.py -v`
Expected: FAIL with `ModuleNotFoundError: edge_case_engine.codec`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/codec.py
import base64
import math

def encode(value):
    if isinstance(value, bool):            # bool before int
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return {"$t": "float", "$v": "nan"}
        if math.isinf(value):
            return {"$t": "float", "$v": "inf" if value > 0 else "-inf"}
        return value
    if value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, bytes):
        return {"$t": "bytes", "$v": base64.b64encode(value).decode("ascii")}
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, tuple):
        return {"$t": "tuple", "$v": [encode(v) for v in value]}
    if isinstance(value, set):
        return {"$t": "set", "$v": [encode(v) for v in sorted(value, key=repr)]}
    if isinstance(value, dict):
        return {"$t": "dict", "$v": [[encode(k), encode(v)] for k, v in value.items()]}
    raise TypeError(f"codec cannot encode {type(value)!r}")

def decode(obj):
    if isinstance(obj, dict):
        t = obj.get("$t")
        if t == "float":
            return {"nan": float("nan"), "inf": float("inf"), "-inf": float("-inf")}[obj["$v"]]
        if t == "bytes":
            return base64.b64decode(obj["$v"])
        if t == "tuple":
            return tuple(decode(v) for v in obj["$v"])
        if t == "set":
            return set(decode(v) for v in obj["$v"])
        if t == "dict":
            return {decode(k): decode(v) for k, v in obj["$v"]}
        raise ValueError(f"unknown codec tag {t!r}")
    if isinstance(obj, list):
        return [decode(v) for v in obj]
    return obj

def values_equal(a, b) -> bool:
    """Structural equality that treats nan as equal to nan and is type-strict for bool/int/float."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(values_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, set):
        sa = sorted(a, key=repr); sb = sorted(b, key=repr)
        return len(sa) == len(sb) and all(values_equal(x, y) for x, y in zip(sa, sb))
    if isinstance(a, dict):
        ka = sorted(a.keys(), key=repr); kb = sorted(b.keys(), key=repr)
        if len(ka) != len(kb) or not all(values_equal(x, y) for x, y in zip(ka, kb)):
            return False
        return all(values_equal(a[x], b[y]) for x, y in zip(ka, kb))
    return a == b
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_codec.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/codec.py tests/test_codec.py
git commit -m "feat: add tagged codec with nan-aware value equality"
```

---

### Task 4: Handler base + FloatHandler

**Files:**
- Create: `type_handlers/base.py`, `type_handlers/scalars.py`
- Test: `tests/test_scalar_handlers.py`

**Interfaces:**
- Consumes: `GenerationBudget` (Task 1).
- Produces: `Handler` ABC with `generate(rng, budget)`, `edge_cases() -> Iterator`, `type_sig() -> str`, `descriptor() -> dict`. `FloatHandler` implementing all four; `descriptor()` returns `{"k": "float"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scalar_handlers.py
import math, random
from edge_case_engine.budget import GenerationBudget
from type_handlers.scalars import FloatHandler

def test_float_generate_is_deterministic():
    b = GenerationBudget()
    v1 = FloatHandler().generate(random.Random(11), b)
    v2 = FloatHandler().generate(random.Random(11), b)
    assert (v1 == v2) or (math.isnan(v1) and math.isnan(v2))

def test_float_edge_cases_first_values_and_descriptor():
    first = list(_take(FloatHandler().edge_cases(), 3))
    assert 0.0 in first
    assert FloatHandler().descriptor() == {"k": "float"}
    assert FloatHandler().type_sig() == "float"

def _take(it, n):
    out = []
    for i, x in enumerate(it):
        if i >= n: break
        out.append(x)
    return out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scalar_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError: type_handlers.scalars`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/base.py
import random
from typing import Any, Iterator
from edge_case_engine.budget import GenerationBudget

class Handler:
    def generate(self, rng: random.Random, budget: GenerationBudget) -> Any:
        raise NotImplementedError
    def edge_cases(self) -> Iterator[Any]:
        raise NotImplementedError
    def type_sig(self) -> str:
        raise NotImplementedError
    def descriptor(self) -> dict:
        raise NotImplementedError
```

```python
# type_handlers/scalars.py
import random, sys
from typing import Iterator
from type_handlers.base import Handler

class FloatHandler(Handler):
    _SPECIALS = (0.0, -0.0, float("inf"), float("-inf"), float("nan"),
                 sys.float_info.max, sys.float_info.min)

    def generate(self, rng, budget):
        if rng.random() < 0.25:
            return rng.choice(self._SPECIALS)
        return rng.uniform(-1e6, 1e6)

    def edge_cases(self) -> Iterator:
        for v in self._SPECIALS:
            yield v

    def type_sig(self) -> str:
        return "float"

    def descriptor(self) -> dict:
        return {"k": "float"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scalar_handlers.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/base.py type_handlers/scalars.py tests/test_scalar_handlers.py
git commit -m "feat: add Handler base and FloatHandler"
```

---

### Task 5: Remaining scalar handlers

**Files:**
- Modify: `type_handlers/scalars.py`
- Test: `tests/test_scalar_handlers.py` (append)

**Interfaces:**
- Consumes: `Handler` (Task 4).
- Produces: `IntegerHandler` (sig `int`, desc `{"k":"int"}`), `StringHandler` (`str`/`{"k":"str"}`), `BoolHandler` (`bool`/`{"k":"bool"}`), `NoneHandler` (`None`/`{"k":"none"}`). All deterministic; `StringHandler.generate` respects `budget.max_string_length`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scalar_handlers.py  (append)
import random
from edge_case_engine.budget import GenerationBudget
from type_handlers.scalars import IntegerHandler, StringHandler, BoolHandler, NoneHandler

def test_int_bool_none_determinism_and_sigs():
    b = GenerationBudget()
    assert IntegerHandler().generate(random.Random(3), b) == IntegerHandler().generate(random.Random(3), b)
    assert BoolHandler().generate(random.Random(3), b) == BoolHandler().generate(random.Random(3), b)
    assert NoneHandler().generate(random.Random(3), b) is None
    assert (IntegerHandler().type_sig(), BoolHandler().type_sig(), NoneHandler().type_sig()) == ("int", "bool", "None")

def test_string_respects_budget_length():
    b = GenerationBudget(max_string_length=5)
    s = StringHandler().generate(random.Random(99), b)
    assert isinstance(s, str) and len(s) <= 5
    assert StringHandler().descriptor() == {"k": "str"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scalar_handlers.py -v`
Expected: FAIL with `ImportError: cannot import name 'IntegerHandler'`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/scalars.py  (append)
class IntegerHandler(Handler):
    _EDGE = (0, 1, -1, sys.maxsize, -sys.maxsize - 1, 2**31 - 1, -2**31, 2**63 - 1, -2**63, 10**18)

    def generate(self, rng, budget):
        if rng.random() < 0.25:
            return rng.choice(self._EDGE)
        return rng.randint(-(2**32), 2**32)

    def edge_cases(self):
        for v in self._EDGE:
            yield v

    def type_sig(self):
        return "int"

    def descriptor(self):
        return {"k": "int"}

class StringHandler(Handler):
    _EDGE = ("", " ", "\t", "\n", "\0", "ud83dudd25", "u4f60u597d", "' OR 1=1 --", "<script>")
    _ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789 _-"

    def generate(self, rng, budget):
        if rng.random() < 0.25:
            choice = rng.choice(self._EDGE)
            return choice[: budget.max_string_length]
        n = rng.randint(0, budget.max_string_length)
        return "".join(rng.choice(self._ALPHABET) for _ in range(n))

    def edge_cases(self):
        for v in self._EDGE:
            yield v

    def type_sig(self):
        return "str"

    def descriptor(self):
        return {"k": "str"}

class BoolHandler(Handler):
    def generate(self, rng, budget):
        return rng.choice([True, False])

    def edge_cases(self):
        yield True
        yield False

    def type_sig(self):
        return "bool"

    def descriptor(self):
        return {"k": "bool"}

class NoneHandler(Handler):
    def generate(self, rng, budget):
        return None

    def edge_cases(self):
        yield None

    def type_sig(self):
        return "None"

    def descriptor(self):
        return {"k": "none"}
```

> Note: the `ud83d`/`u4f60` sequences above are placeholders for the literal emoji/unicode strings
> already used in the current `string_handler.py` — copy the real `"🔥"`, `"你好"` literals from that
> file when implementing.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_scalar_handlers.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/scalars.py tests/test_scalar_handlers.py
git commit -m "feat: add Integer/String/Bool/None handlers"
```

---

### Task 6: OptionalHandler

**Files:**
- Create: `type_handlers/optional_handler.py`
- Test: `tests/test_composite_handlers.py`

**Interfaces:**
- Consumes: `Handler` (Task 4).
- Produces: `OptionalHandler(inner: Handler)` with attr `.inner`; `generate` returns `None` with prob `budget.probability_none` else `inner.generate`; `descriptor() -> {"k":"optional","inner": inner.descriptor()}`; `type_sig() -> "Optional[<inner>]"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_composite_handlers.py
import random
from edge_case_engine.budget import GenerationBudget
from type_handlers.scalars import IntegerHandler
from type_handlers.optional_handler import OptionalHandler

def test_optional_can_yield_none_and_inner():
    h = OptionalHandler(IntegerHandler())
    b = GenerationBudget(probability_none=1.0)
    assert h.generate(random.Random(1), b) is None
    b2 = GenerationBudget(probability_none=0.0)
    assert isinstance(h.generate(random.Random(1), b2), int)
    assert h.descriptor() == {"k": "optional", "inner": {"k": "int"}}
    assert h.type_sig() == "Optional[int]"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_composite_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError: type_handlers.optional_handler`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/optional_handler.py
from type_handlers.base import Handler

class OptionalHandler(Handler):
    def __init__(self, inner: Handler):
        self.inner = inner

    def generate(self, rng, budget):
        if rng.random() < budget.probability_none:
            return None
        return self.inner.generate(rng, budget)

    def edge_cases(self):
        yield None
        for v in self.inner.edge_cases():
            yield v

    def type_sig(self):
        return f"Optional[{self.inner.type_sig()}]"

    def descriptor(self):
        return {"k": "optional", "inner": self.inner.descriptor()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_composite_handlers.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/optional_handler.py tests/test_composite_handlers.py
git commit -m "feat: add OptionalHandler"
```

---

### Task 7: UnionHandler

**Files:**
- Create: `type_handlers/union_handler.py`
- Test: `tests/test_composite_handlers.py` (append)

**Interfaces:**
- Consumes: `Handler` (Task 4).
- Produces: `UnionHandler(options: list[Handler])` with attr `.options`; weighted choice via `budget.union_weights` (uniform if empty); `descriptor() -> {"k":"union","options":[...]}`; `type_sig() -> "Union[a, b]"`; `edge_cases` round-robins the first edge of each option.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_composite_handlers.py  (append)
from type_handlers.scalars import IntegerHandler, StringHandler
from type_handlers.union_handler import UnionHandler

def test_union_generates_one_of_the_options():
    h = UnionHandler([IntegerHandler(), StringHandler()])
    b = GenerationBudget()
    vals = [h.generate(random.Random(s), b) for s in range(20)]
    assert any(isinstance(v, int) for v in vals)
    assert any(isinstance(v, str) for v in vals)
    assert h.descriptor() == {"k": "union", "options": [{"k": "int"}, {"k": "str"}]}
    assert h.type_sig() == "Union[int, str]"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_composite_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError: type_handlers.union_handler`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/union_handler.py
from type_handlers.base import Handler

class UnionHandler(Handler):
    def __init__(self, options):
        self.options = list(options)

    def generate(self, rng, budget):
        weights = list(budget.union_weights) if budget.union_weights else None
        if weights and len(weights) == len(self.options):
            chosen = rng.choices(self.options, weights=weights, k=1)[0]
        else:
            chosen = rng.choice(self.options)
        return chosen.generate(rng, budget)

    def edge_cases(self):
        iters = [o.edge_cases() for o in self.options]
        exhausted = 0
        while exhausted < len(iters):
            exhausted = 0
            for it in iters:
                try:
                    yield next(it)
                except StopIteration:
                    exhausted += 1

    def type_sig(self):
        return "Union[" + ", ".join(o.type_sig() for o in self.options) + "]"

    def descriptor(self):
        return {"k": "union", "options": [o.descriptor() for o in self.options]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_composite_handlers.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/union_handler.py tests/test_composite_handlers.py
git commit -m "feat: add UnionHandler"
```

---

### Task 8: ListHandler

**Files:**
- Create: `type_handlers/list_handler.py`
- Test: `tests/test_composite_handlers.py` (append)

**Interfaces:**
- Consumes: `Handler` (Task 4), `GenerationBudget` (Task 1).
- Produces: `ListHandler(elem: Handler)` with attr `.elem`; `generate` produces a list of length `0..budget.max_list_length`, charging the accountant and recursing with `budget.child()`; stops growing when `budget.spend()` returns `False` or `budget.depth_exhausted()`; `descriptor() -> {"k":"list","elem":...}`; `type_sig() -> "list[<elem>]"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_composite_handlers.py  (append)
from type_handlers.list_handler import ListHandler

def test_list_generates_within_budget_and_is_deterministic():
    h = ListHandler(IntegerHandler())
    b1 = GenerationBudget(max_list_length=4, max_total_nodes=100)
    b2 = GenerationBudget(max_list_length=4, max_total_nodes=100)
    v1 = h.generate(random.Random(5), b1)
    v2 = h.generate(random.Random(5), b2)
    assert v1 == v2
    assert isinstance(v1, list) and len(v1) <= 4
    assert h.type_sig() == "list[int]"

def test_list_stops_when_depth_exhausted():
    h = ListHandler(IntegerHandler())
    b = GenerationBudget(max_depth=0)
    assert h.generate(random.Random(5), b) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_composite_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError: type_handlers.list_handler`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/list_handler.py
from type_handlers.base import Handler

class ListHandler(Handler):
    def __init__(self, elem: Handler):
        self.elem = elem

    def generate(self, rng, budget):
        if budget.depth_exhausted():
            return []
        length = rng.randint(0, budget.max_list_length)
        child = budget.child()
        out = []
        for _ in range(length):
            if not budget.spend(1):
                break
            out.append(self.elem.generate(rng, child))
        return out

    def edge_cases(self):
        yield []
        for v in self.elem.edge_cases():
            yield [v]

    def type_sig(self):
        return f"list[{self.elem.type_sig()}]"

    def descriptor(self):
        return {"k": "list", "elem": self.elem.descriptor()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_composite_handlers.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/list_handler.py tests/test_composite_handlers.py
git commit -m "feat: add ListHandler with budget-bounded generation"
```

---

### Task 9: DictHandler

**Files:**
- Create: `type_handlers/dict_handler.py`
- Test: `tests/test_composite_handlers.py` (append)

**Interfaces:**
- Consumes: `Handler` (Task 4), `GenerationBudget` (Task 1).
- Produces: `DictHandler(key: Handler, val: Handler)` with attrs `.key`, `.val`; `generate` produces a dict of `0..budget.max_dict_keys` entries, charging accountant + `budget.child()`; `descriptor() -> {"k":"dict","key":...,"val":...}`; `type_sig() -> "dict[<k>, <v>]"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_composite_handlers.py  (append)
from type_handlers.dict_handler import DictHandler
from type_handlers.scalars import StringHandler

def test_dict_generates_within_budget_and_is_deterministic():
    h = DictHandler(StringHandler(), IntegerHandler())
    b1 = GenerationBudget(max_dict_keys=3, max_total_nodes=100)
    b2 = GenerationBudget(max_dict_keys=3, max_total_nodes=100)
    v1 = h.generate(random.Random(8), b1)
    v2 = h.generate(random.Random(8), b2)
    assert v1 == v2
    assert isinstance(v1, dict) and len(v1) <= 3
    assert h.type_sig() == "dict[str, int]"
    assert h.descriptor() == {"k": "dict", "key": {"k": "str"}, "val": {"k": "int"}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_composite_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError: type_handlers.dict_handler`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/dict_handler.py
from type_handlers.base import Handler

class DictHandler(Handler):
    def __init__(self, key: Handler, val: Handler):
        self.key = key
        self.val = val

    def generate(self, rng, budget):
        if budget.depth_exhausted():
            return {}
        n = rng.randint(0, budget.max_dict_keys)
        child = budget.child()
        out = {}
        for _ in range(n):
            if not budget.spend(1):
                break
            k = self.key.generate(rng, child)
            try:
                out[k] = self.val.generate(rng, child)
            except TypeError:
                # unhashable generated key — skip this entry deterministically
                continue
        return out

    def edge_cases(self):
        yield {}

    def type_sig(self):
        return f"dict[{self.key.type_sig()}, {self.val.type_sig()}]"

    def descriptor(self):
        return {"k": "dict", "key": self.key.descriptor(), "val": self.val.descriptor()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_composite_handlers.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/dict_handler.py tests/test_composite_handlers.py
git commit -m "feat: add DictHandler with budget-bounded generation"
```

---

### Task 10: TypeResolver

**Files:**
- Create: `type_handlers/resolver.py`
- Test: `tests/test_resolver.py`

**Interfaces:**
- Consumes: all handlers (Tasks 4–9).
- Produces: `TypeResolver` with classmethods `resolve(annotation, strict=False) -> Handler`, `from_descriptor(desc) -> Handler`, and instance API `r = TypeResolver(); r.resolve_tracked(ann) -> Handler` plus `r.fallback_rate() -> float`. Mapping per spec §4.2. Unknown/unannotated → `FloatHandler` fallback (record a fallback event; raise `TypeError` if `strict`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resolver.py
from typing import Optional, Union, List, Dict
from type_handlers.resolver import TypeResolver

def test_resolves_nested_types():
    h = TypeResolver.resolve(List[Dict[str, int]])
    assert h.type_sig() == "list[dict[str, int]]"
    assert TypeResolver.resolve(Optional[int]).type_sig() == "Optional[int]"
    assert TypeResolver.resolve(Union[int, str]).type_sig() == "Union[int, str]"

def test_descriptor_roundtrip():
    h = TypeResolver.resolve(List[Optional[int]])
    rebuilt = TypeResolver.from_descriptor(h.descriptor())
    assert rebuilt.type_sig() == h.type_sig()

def test_fallback_rate_tracked():
    r = TypeResolver()
    r.resolve_tracked(int)
    r.resolve_tracked(object)      # unknown -> fallback
    assert r.fallback_rate() == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_resolver.py -v`
Expected: FAIL with `ModuleNotFoundError: type_handlers.resolver`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/resolver.py
import typing
from type_handlers.scalars import (
    FloatHandler, IntegerHandler, StringHandler, BoolHandler, NoneHandler,
)
from type_handlers.list_handler import ListHandler
from type_handlers.dict_handler import DictHandler
from type_handlers.optional_handler import OptionalHandler
from type_handlers.union_handler import UnionHandler

_NONE = type(None)
_SCALARS = {float: FloatHandler, int: IntegerHandler, str: StringHandler, bool: BoolHandler}

class TypeResolver:
    def __init__(self):
        self._total = 0
        self._fallbacks = 0

    # ---- instance tracking wrapper ----
    def resolve_tracked(self, annotation, strict=False):
        self._total += 1
        before = _FallbackCounter.count
        handler = self.resolve(annotation, strict=strict)
        if _FallbackCounter.count > before:
            self._fallbacks += 1
        return handler

    def fallback_rate(self) -> float:
        return 0.0 if self._total == 0 else self._fallbacks / self._total

    # ---- core resolution ----
    @classmethod
    def resolve(cls, annotation, strict=False):
        if annotation in (None, _NONE):
            return NoneHandler()
        if annotation in _SCALARS:
            return _SCALARS[annotation]()

        origin = typing.get_origin(annotation)
        args = typing.get_args(annotation)

        if origin in (list,):
            return ListHandler(cls.resolve(args[0], strict) if args else FloatHandler())
        if origin in (dict,):
            if len(args) == 2:
                return DictHandler(cls.resolve(args[0], strict), cls.resolve(args[1], strict))
            return DictHandler(StringHandler(), FloatHandler())
        if origin is typing.Union:
            non_none = [a for a in args if a is not _NONE]
            has_none = len(non_none) != len(args)
            inner = (cls.resolve(non_none[0], strict) if len(non_none) == 1
                     else UnionHandler([cls.resolve(a, strict) for a in non_none]))
            return OptionalHandler(inner) if has_none else inner

        # unknown / unannotated
        if strict:
            raise TypeError(f"no handler for annotation {annotation!r}")
        _FallbackCounter.count += 1
        return FloatHandler()

    @classmethod
    def from_descriptor(cls, desc):
        k = desc["k"]
        if k == "float": return FloatHandler()
        if k == "int": return IntegerHandler()
        if k == "str": return StringHandler()
        if k == "bool": return BoolHandler()
        if k == "none": return NoneHandler()
        if k == "list": return ListHandler(cls.from_descriptor(desc["elem"]))
        if k == "dict": return DictHandler(cls.from_descriptor(desc["key"]), cls.from_descriptor(desc["val"]))
        if k == "optional": return OptionalHandler(cls.from_descriptor(desc["inner"]))
        if k == "union": return UnionHandler([cls.from_descriptor(o) for o in desc["options"]])
        raise ValueError(f"unknown descriptor kind {k!r}")

class _FallbackCounter:
    count = 0
```

> Note on `bool`/`int`: `bool` is a subclass of `int`; the `_SCALARS` dict lookup is by exact key
> identity, so `bool` resolves to `BoolHandler` and `int` to `IntegerHandler` correctly.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_resolver.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/resolver.py tests/test_resolver.py
git commit -m "feat: add TypeResolver with descriptor round-trip and fallback tracking"
```

---

### Task 11: Recipe, materialize, base replay

**Files:**
- Create: `edge_case_engine/recipe.py`
- Test: `tests/test_recipe.py`

**Interfaces:**
- Consumes: `TypeResolver` (Task 10), `GenerationBudget` (Task 1), `codec` (Task 3).
- Produces: `LineageOp(op: str, path: list, args: dict)` (dataclass); `Recipe(descriptor: dict, seed: int, budget: dict, lineage: list)` (dataclass) with `.type_sig()`, `.to_dict()`, `from_dict`; `materialize(recipe) -> value` that replays **base only** (empty/ignored lineage handled in Task 14).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recipe.py
from typing import List, Dict
from edge_case_engine.budget import GenerationBudget
from edge_case_engine.recipe import Recipe, materialize
from edge_case_engine.codec import values_equal
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recipe.py -v`
Expected: FAIL with `ModuleNotFoundError: edge_case_engine.recipe`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/recipe.py
import random
from dataclasses import dataclass, field, asdict
from edge_case_engine.budget import GenerationBudget
from type_handlers.resolver import TypeResolver

@dataclass
class LineageOp:
    op: str
    path: list = field(default_factory=list)
    args: dict = field(default_factory=dict)

@dataclass
class Recipe:
    descriptor: dict
    seed: int
    budget: dict
    lineage: list = field(default_factory=list)

    def type_sig(self) -> str:
        return TypeResolver.from_descriptor(self.descriptor).type_sig()

    def to_dict(self) -> dict:
        return {
            "descriptor": self.descriptor,
            "seed": self.seed,
            "budget": self.budget,
            "lineage": [asdict(op) if isinstance(op, LineageOp) else op for op in self.lineage],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Recipe":
        lineage = [LineageOp(**op) for op in d.get("lineage", [])]
        return cls(descriptor=d["descriptor"], seed=d["seed"], budget=d["budget"], lineage=lineage)

def materialize_base(recipe: "Recipe"):
    """Replay the BASE input (no lineage applied)."""
    handler = TypeResolver.from_descriptor(recipe.descriptor)
    budget = GenerationBudget.from_dict(recipe.budget)
    return handler.generate(random.Random(recipe.seed), budget)

def materialize(recipe: "Recipe"):
    """Full replay. Lineage application is added in Task 14; base only for now."""
    return materialize_base(recipe)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_recipe.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/recipe.py tests/test_recipe.py
git commit -m "feat: add Recipe and deterministic base materialization"
```

---

### Task 12: Mutator base, registry, ScalarMutator

**Files:**
- Create: `edge_case_engine/mutators/__init__.py`, `edge_case_engine/mutators/base.py`, `edge_case_engine/mutators/scalar.py`, `edge_case_engine/mutators/registry.py`
- Test: `tests/test_mutators.py`

**Interfaces:**
- Consumes: handlers (Tasks 4–9), `codec` (Task 3), `LineageOp` (Task 11).
- Produces: `Mutator` base with `can_mutate(handler, value) -> bool` and `mutate(handler, value, rng, budget, path) -> (new_value, LineageOp)`; `ScalarMutator` (op `"scalar.replace"`); `MutatorRegistry.choose(handler, value, rng) -> Mutator`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mutators.py
import random
from edge_case_engine.budget import GenerationBudget
from edge_case_engine.mutators.scalar import ScalarMutator
from type_handlers.scalars import IntegerHandler

def test_scalar_mutator_replaces_and_records_op():
    m = ScalarMutator()
    h = IntegerHandler()
    new_value, op = m.mutate(h, 5, random.Random(2), GenerationBudget(), path=[])
    assert op.op == "scalar.replace"
    assert op.path == []
    assert "value" in op.args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mutators.py -v`
Expected: FAIL with `ModuleNotFoundError: edge_case_engine.mutators.scalar`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/mutators/__init__.py
```

```python
# edge_case_engine/mutators/base.py
class Mutator:
    def can_mutate(self, handler, value) -> bool:
        raise NotImplementedError
    def mutate(self, handler, value, rng, budget, path):
        """Return (new_value, LineageOp). path locates `value` within the root input."""
        raise NotImplementedError
```

```python
# edge_case_engine/mutators/scalar.py
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
```

```python
# edge_case_engine/mutators/registry.py
from edge_case_engine.mutators.scalar import ScalarMutator

class MutatorRegistry:
    def __init__(self, mutators=None):
        # Order matters: more specific (collection) mutators are registered ahead of scalar
        # once Task 13 adds them. For now scalar handles everything non-container.
        self._mutators = mutators if mutators is not None else [ScalarMutator()]

    def applicable(self, handler, value):
        return [m for m in self._mutators if m.can_mutate(handler, value)]

    def choose(self, handler, value, rng):
        candidates = self.applicable(handler, value)
        return rng.choice(candidates) if candidates else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_mutators.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/mutators tests/test_mutators.py
git commit -m "feat: add Mutator base, registry, and ScalarMutator"
```

---

### Task 13: ListMutator and DictMutator

**Files:**
- Create: `edge_case_engine/mutators/collection.py`
- Modify: `edge_case_engine/mutators/registry.py` (register collection mutators first)
- Test: `tests/test_mutators.py` (append)

**Interfaces:**
- Consumes: `Mutator` (Task 12), handlers (Tasks 8–9), `codec` (Task 3).
- Produces: `ListMutator` (ops `list.insert|delete|duplicate|reverse|empty`), `DictMutator` (ops `dict.drop_key|add_key|corrupt_value`). Each returns `(new_value, LineageOp)` with encoded literal args. Type-aware ops use `handler.elem` / `handler.key` / `handler.val` to generate new typed values.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mutators.py  (append)
from edge_case_engine.mutators.collection import ListMutator, DictMutator
from type_handlers.list_handler import ListHandler
from type_handlers.dict_handler import DictHandler
from type_handlers.scalars import StringHandler

def test_list_mutator_changes_list_and_records_op():
    h = ListHandler(IntegerHandler())
    new_value, op = ListMutator().mutate(h, [1, 2, 3], random.Random(4), GenerationBudget(), path=[])
    assert op.op.startswith("list.")
    assert isinstance(new_value, list)
    assert new_value != [1, 2, 3] or op.op == "reverse"  # some structural change happened

def test_dict_mutator_changes_dict_and_records_op():
    h = DictHandler(StringHandler(), IntegerHandler())
    new_value, op = DictMutator().mutate(h, {"a": 1}, random.Random(4), GenerationBudget(), path=[])
    assert op.op.startswith("dict.")
    assert isinstance(new_value, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mutators.py -v`
Expected: FAIL with `ModuleNotFoundError: edge_case_engine.mutators.collection`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/mutators/collection.py
from edge_case_engine.mutators.base import Mutator
from edge_case_engine.recipe import LineageOp
from edge_case_engine.codec import encode

class ListMutator(Mutator):
    def can_mutate(self, handler, value) -> bool:
        return isinstance(value, list)

    def mutate(self, handler, value, rng, budget, path):
        new = list(value)
        ops = ["insert", "delete", "duplicate", "reverse", "empty"]
        op = rng.choice(ops)
        args = {}
        elem_handler = getattr(handler, "elem", None)
        if op == "insert":
            idx = rng.randint(0, len(new))
            elem = elem_handler.generate(rng, budget.child()) if elem_handler else rng.randint(-1, 1)
            new.insert(idx, elem)
            args = {"index": idx, "value": encode(elem)}
        elif op == "delete" and new:
            idx = rng.randrange(len(new))
            del new[idx]
            args = {"index": idx}
        elif op == "duplicate" and new:
            idx = rng.randrange(len(new))
            new.insert(idx, new[idx])
            args = {"index": idx}
        elif op == "reverse":
            new.reverse()
        elif op == "empty":
            new = []
        else:  # delete/duplicate on empty list -> fall back to insert of None
            op = "insert"; new.insert(0, None); args = {"index": 0, "value": encode(None)}
        return new, LineageOp(op=f"list.{op}", path=list(path), args=args)

class DictMutator(Mutator):
    def can_mutate(self, handler, value) -> bool:
        return isinstance(value, dict)

    def mutate(self, handler, value, rng, budget, path):
        new = dict(value)
        key_handler = getattr(handler, "key", None)
        val_handler = getattr(handler, "val", None)
        ops = ["drop_key", "add_key", "corrupt_value"]
        op = rng.choice(ops)
        args = {}
        keys = list(new.keys())
        if op == "drop_key" and keys:
            k = rng.choice(keys)
            del new[k]
            args = {"key": encode(k)}
        elif op == "add_key":
            k = key_handler.generate(rng, budget.child()) if key_handler else "k"
            v = val_handler.generate(rng, budget.child()) if val_handler else 0
            new[k] = v
            args = {"key": encode(k), "value": encode(v)}
        elif op == "corrupt_value" and keys:
            k = rng.choice(keys)
            corrupt = rng.choice([None, "synthedge", float("nan")])
            new[k] = corrupt
            args = {"key": encode(k), "value": encode(corrupt)}
        else:  # drop/corrupt on empty dict -> add_key
            op = "add_key"; new["synthedge"] = None
            args = {"key": encode("synthedge"), "value": encode(None)}
        return new, LineageOp(op=f"dict.{op}", path=list(path), args=args)
```

```python
# edge_case_engine/mutators/registry.py  (replace default list)
from edge_case_engine.mutators.scalar import ScalarMutator
from edge_case_engine.mutators.collection import ListMutator, DictMutator

class MutatorRegistry:
    def __init__(self, mutators=None):
        self._mutators = mutators if mutators is not None else [ListMutator(), DictMutator(), ScalarMutator()]

    def applicable(self, handler, value):
        return [m for m in self._mutators if m.can_mutate(handler, value)]

    def choose(self, handler, value, rng):
        candidates = self.applicable(handler, value)
        return rng.choice(candidates) if candidates else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_mutators.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/mutators/collection.py edge_case_engine/mutators/registry.py tests/test_mutators.py
git commit -m "feat: add List/Dict structure-aware mutators"
```

---

### Task 14: Lineage application + full replay

**Files:**
- Modify: `edge_case_engine/recipe.py` (add `apply_lineage_op`, update `materialize`)
- Test: `tests/test_recipe.py` (append)

**Interfaces:**
- Consumes: `LineageOp`/`Recipe` (Task 11), `codec.decode` (Task 3).
- Produces: `apply_lineage_op(value, op: LineageOp) -> value`; `materialize(recipe)` now applies the full lineage in order. Lineage ops operate at top-level `path == []` for Slice 1 (RecursiveMutator's nested paths are deferred — see note).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recipe.py  (append)
from edge_case_engine.recipe import LineageOp, apply_lineage_op, materialize, Recipe
from edge_case_engine.codec import encode, values_equal
from edge_case_engine.budget import GenerationBudget

def test_apply_scalar_replace():
    out = apply_lineage_op(5, LineageOp("scalar.replace", [], {"value": encode(None)}))
    assert out is None

def test_full_materialize_applies_lineage_in_order():
    r = Recipe(descriptor={"k": "list", "elem": {"k": "int"}}, seed=1,
               budget=GenerationBudget().to_dict(),
               lineage=[LineageOp("list.empty", [], {}),
                        LineageOp("list.insert", [], {"index": 0, "value": encode(99)})])
    assert values_equal(materialize(r), [99])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_recipe.py::test_apply_scalar_replace -v`
Expected: FAIL with `ImportError: cannot import name 'apply_lineage_op'`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/recipe.py  (add near bottom, and update materialize)
from edge_case_engine.codec import decode

def apply_lineage_op(value, op):
    """Apply one LineageOp to the root value (Slice 1: path == [])."""
    name = op.op
    args = op.args
    if name == "scalar.replace":
        return decode(args["value"])
    if name == "list.insert":
        value = list(value); value.insert(args["index"], decode(args["value"])); return value
    if name == "list.delete":
        value = list(value); del value[args["index"]]; return value
    if name == "list.duplicate":
        value = list(value); value.insert(args["index"], value[args["index"]]); return value
    if name == "list.reverse":
        value = list(value); value.reverse(); return value
    if name == "list.empty":
        return []
    if name == "dict.drop_key":
        value = dict(value); value.pop(decode(args["key"]), None); return value
    if name == "dict.add_key":
        value = dict(value); value[decode(args["key"])] = decode(args["value"]); return value
    if name == "dict.corrupt_value":
        value = dict(value); value[decode(args["key"])] = decode(args["value"]); return value
    raise ValueError(f"unknown lineage op {name!r}")

def materialize(recipe):
    value = materialize_base(recipe)
    for op in recipe.lineage:
        if not isinstance(op, LineageOp):
            op = LineageOp(**op)
        value = apply_lineage_op(value, op)
    return value
```

> **Slice 1 scope note (spec R-2):** mutation is applied at the **root** of each input
> (`path == []`); `RecursiveMutator` and nested-path replay are explicitly deferred to a later slice.
> This keeps lineage application total and testable now. The `path` field is preserved in the data
> model so nested support is additive later.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_recipe.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/recipe.py tests/test_recipe.py
git commit -m "feat: apply mutation lineage for full recipe replay"
```

---

### Task 15: Sampling-based EdgeCaseEngine

**Files:**
- Modify: `edge_case_engine/engine.py`
- Test: `tests/test_engine_generation.py`

**Interfaces:**
- Consumes: handlers (Tasks 4–9), `GenerationBudget` (Task 1), `Recipe` (Task 11).
- Produces: `EdgeCaseEngine.generate_seeds(handlers: list, master_rng, budget, n_random=20) -> list[tuple[input_tuple, list[Recipe]]]`. Each returned item is `(input_tuple, recipes)` where `input_tuple` is the materialized args and `recipes` is one `Recipe` per parameter. Per-parameter seed = `master_rng.getrandbits(64)` so each recipe replays independently. Keeps `self.mutation` attribute pointing at a `MutatorRegistry` for the fuzz loop (Task 17).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine_generation.py
import random
from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.budget import GenerationBudget
from edge_case_engine.recipe import materialize
from edge_case_engine.codec import values_equal
from type_handlers.scalars import IntegerHandler
from type_handlers.list_handler import ListHandler

def test_generate_seeds_recipes_replay_to_inputs():
    engine = EdgeCaseEngine()
    handlers = [IntegerHandler(), ListHandler(IntegerHandler())]
    seeds = engine.generate_seeds(handlers, random.Random(42), GenerationBudget(), n_random=5)
    assert seeds
    for input_tuple, recipes in seeds:
        assert len(recipes) == len(handlers)
        replayed = tuple(materialize(r) for r in recipes)
        assert values_equal(list(replayed), list(input_tuple))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_engine_generation.py -v`
Expected: FAIL with `AttributeError: 'EdgeCaseEngine' object has no attribute 'generate_seeds'`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/engine.py  (replace file contents)
import random
from itertools import islice
from edge_case_engine.recipe import Recipe
from edge_case_engine.mutators.registry import MutatorRegistry

class EdgeCaseEngine:
    def __init__(self):
        self.mutation = MutatorRegistry()

    def _param_recipe(self, handler, master_rng, budget):
        seed = master_rng.getrandbits(64)
        return Recipe(descriptor=handler.descriptor(), seed=seed, budget=budget.to_dict(), lineage=[])

    def generate_seeds(self, handlers, master_rng, budget, n_random=20):
        """Produce (input_tuple, [Recipe per param]) seeds.
        Strategy: a bounded set of edge-case combinations + n_random sampled combinations."""
        from edge_case_engine.recipe import materialize
        seeds = []
        seen = set()

        def add(recipes):
            inp = tuple(materialize(r) for r in recipes)
            key = repr(inp)
            if key in seen:
                return
            seen.add(key)
            seeds.append((inp, recipes))

        # n_random sampled combinations (one fresh recipe per param)
        for _ in range(n_random):
            recipes = [self._param_recipe(h, master_rng, budget) for h in handlers]
            add(recipes)

        return seeds
```

> Note: `combinatorial.py` is no longer imported by the engine. Leave the file in place for this
> slice; its removal is a separate cleanup.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_engine_generation.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/engine.py tests/test_engine_generation.py
git commit -m "feat: sampling-based seed generation producing replayable recipes"
```

---

### Task 16: Versioned CorpusManager v2

**Files:**
- Modify: `edge_case_engine/corpus.py`
- Test: `tests/test_corpus_v2.py`

**Interfaces:**
- Consumes: `Recipe` (Task 11/14), `codec` (Task 3).
- Produces: `CorpusManager(root=".synthedge")` with `make_envelope(recipe, input_value, artifacts=None) -> dict`, `save_interesting(envelope)`, `save_crash(envelope)`, `load_interesting() -> list[dict]` (integrity-checked: replays each recipe and raises `CorpusIntegrityError` on mismatch). Envelope schema per spec §4.7 (`version=1`). Existing methods used by legacy `main.py` remain importable but are not the focus here.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corpus_v2.py
import tempfile, os
from edge_case_engine.corpus import CorpusManager
from edge_case_engine.recipe import Recipe
from edge_case_engine.budget import GenerationBudget

def test_envelope_roundtrip_with_integrity():
    with tempfile.TemporaryDirectory() as d:
        cm = CorpusManager(root=os.path.join(d, ".synthedge"))
        r = Recipe(descriptor={"k": "int"}, seed=7, budget=GenerationBudget().to_dict(), lineage=[])
        from edge_case_engine.recipe import materialize
        env = cm.make_envelope(r, materialize(r), artifacts={"exception": None})
        assert env["version"] == 1
        cm.save_interesting(env)
        loaded = cm.load_interesting()
        assert len(loaded) == 1
        assert loaded[0]["recipe"]["seed"] == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_corpus_v2.py -v`
Expected: FAIL with `TypeError` (no `root` kwarg) or `AttributeError: make_envelope`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/corpus.py  (add v2 API; keep existing methods intact)
import os, json
from edge_case_engine.codec import encode, values_equal
from edge_case_engine.recipe import Recipe, materialize

class CorpusIntegrityError(Exception):
    pass

# --- extend the existing class; if rewriting, preserve legacy methods used by main.py ---
class CorpusManager:
    def __init__(self, corpus_dir="corpus", root=None):
        self.corpus_dir = corpus_dir
        self.inputs_file = os.path.join(corpus_dir, "inputs.json")
        self.crashes_file = os.path.join(corpus_dir, "crashes.json")
        os.makedirs(self.corpus_dir, exist_ok=True)
        self._seen_hashes = set()
        self.interesting_inputs = []
        # v2 store
        self.root = root or ".synthedge"
        self._interesting_path = os.path.join(self.root, "corpus", "interesting.jsonl")
        self._crashes_path = os.path.join(self.root, "crashes", "crashes.jsonl")
        os.makedirs(os.path.dirname(self._interesting_path), exist_ok=True)
        os.makedirs(os.path.dirname(self._crashes_path), exist_ok=True)

    # ---- v2 envelope API ----
    def make_envelope(self, recipe: Recipe, input_value, artifacts=None) -> dict:
        return {
            "version": 1,
            "seed": recipe.seed,
            "recipe": recipe.to_dict(),
            "input": encode(input_value),
            "artifacts": artifacts or {"output": None, "exception": None, "coverage": None},
        }

    def _append_jsonl(self, path, env):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(env) + "n")

    def save_interesting(self, env):
        self._append_jsonl(self._interesting_path, env)

    def save_crash(self, env):
        self._append_jsonl(self._crashes_path, env)

    def load_interesting(self):
        return self._load_checked(self._interesting_path)

    def load_crashes_v2(self):
        return self._load_checked(self._crashes_path)

    def _load_checked(self, path):
        if not os.path.exists(path):
            return []
        out = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                env = json.loads(line)
                recipe = Recipe.from_dict(env["recipe"])
                from edge_case_engine.codec import decode
                replayed = materialize(recipe)
                cached = decode(env["input"])
                if not values_equal(replayed, cached):
                    raise CorpusIntegrityError(f"recipe replay != cached input (seed={recipe.seed})")
                out.append(env)
        return out
```

> The `"n"` written after each JSON line above is a stand-in for the newline character `\n` — use a
> real newline when implementing. Keep the existing legacy methods (`add_inputs`, `record_crash`,
> `get_crashes`, etc.) in the class so `main.py` still imports cleanly.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_corpus_v2.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/corpus.py tests/test_corpus_v2.py
git commit -m "feat: versioned corpus envelope with integrity-checked replay"
```

---

### Task 17: Executor artifacts + CLI `--seed` wiring

**Files:**
- Modify: `edge_case_engine/executor.py`, `synthedge/cli.py`, `type_handlers/registry.py`
- Test: `tests/test_cli.py` (append a seed-determinism test)

**Interfaces:**
- Consumes: everything above.
- Produces: `FunctionExecutor.execute` unchanged in signature but `ExecutionResult` gains nothing new (artifacts are assembled in the CLI from `result`); `run_fuzzer(module_path, iterations=300, verbose=False, seed=None) -> dict`; CLI flag `--seed`. `type_handlers/registry.py` `HandlerRegistry.handlers_for_params` delegates to `TypeResolver`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py  (append)
import random
from synthedge.cli import run_fuzzer

def test_run_fuzzer_is_deterministic_with_seed(tmp_path):
    target = tmp_path / "t.py"
    target.write_text(
        "from edge_case_engine.contracts import fuzz_contract\n"
        "@fuzz_contract(allowed_exceptions=())\n"
        "def f(xs):\n"
        "    return sum(xs)\n"
    )
    s1 = run_fuzzer(str(target), iterations=30, seed=123)
    s2 = run_fuzzer(str(target), iterations=30, seed=123)
    assert s1 == s2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py::test_run_fuzzer_is_deterministic_with_seed -v`
Expected: FAIL with `TypeError: run_fuzzer() got an unexpected keyword argument 'seed'`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/registry.py  (replace body)
import typing
from type_handlers.resolver import TypeResolver

class HandlerRegistry:
    @classmethod
    def handlers_for_params(cls, parameters, annotations):
        return [TypeResolver.resolve(annotations.get(p, None)) for p in parameters]
```

```python
# synthedge/cli.py  (key edits)
# 1) add imports near the top:
import random
from edge_case_engine.budget import GenerationBudget

# 2) change run_fuzzer signature and seed the master RNG; replace the seed-generation +
#    fuzz loop to use the new engine API. Minimal viable wiring:

def run_fuzzer(module_path, iterations=300, verbose=False, seed=None):
    module = load_module_from_path(module_path)
    targets = TargetDiscovery.discover_modules([module])
    if not targets:
        print(f"No @fuzz_contract targets found in {module_path}")
        return {}

    if seed is None:
        seed = random.randrange(2**63)
    master_rng = random.Random(seed)
    budget = GenerationBudget()

    module_dir = os.path.dirname(os.path.abspath(module_path))
    engine = EdgeCaseEngine()
    executor = FunctionExecutor()
    corpus = CorpusManager(corpus_dir=os.path.join(module_dir, "corpus"),
                           root=os.path.join(module_dir, ".synthedge"))
    summary = {}

    import typing as _typing
    for target in targets:
        try:
            annotations = _typing.get_type_hints(target.function)
        except Exception:
            annotations = {}
        handlers = [
            __import__("type_handlers.resolver", fromlist=["TypeResolver"]).TypeResolver.resolve(
                annotations.get(p, None)) for p in target.parameters
        ]
        seeds = engine.generate_seeds(handlers, master_rng, budget, n_random=max(5, iterations // 3))

        crashes_found = 0
        # pool of (input_tuple, recipes)
        pool = list(seeds)
        for _ in range(iterations):
            if not pool:
                break
            input_tuple, recipes = pool[master_rng.randrange(len(pool))]
            # mutate parameter 0 at root for Slice 1
            h0 = handlers[0]
            mutator = engine.mutation.choose(h0, input_tuple[0], master_rng)
            if mutator is None:
                continue
            new_v0, op = mutator.mutate(h0, input_tuple[0], master_rng, budget, path=[])
            mutated = (new_v0,) + tuple(input_tuple[1:])
            new_recipes = [Recipe.from_dict(recipes[0].to_dict())] + list(recipes[1:])
            new_recipes[0].lineage = list(recipes[0].lineage) + [op]

            results = executor.execute(target.function, [mutated])
            for result in results:
                env = corpus.make_envelope(
                    new_recipes[0], result.input[0] if False else mutated[0],
                    artifacts={"exception": (None if result.error is None
                                             else f"{type(result.error).__name__}: {result.error}"),
                               "coverage": result.coverage_id, "output": None},
                )
                if result.new_path:
                    pool.append((mutated, new_recipes))
                    corpus.save_interesting(env)
                if result.error is not None:
                    corpus.save_crash(env)
                    crashes_found += 1
        summary[target.name] = {"iterations": iterations, "crashes_found": crashes_found}

    print(f"synthedge seed={seed}")
    return summary

# 3) in main(): add the CLI flag and pass it through
#    parser.add_argument("--seed", type=int, default=None, help="Deterministic run seed")
#    summary = run_fuzzer(args.module, iterations=args.iterations, verbose=args.verbose, seed=args.seed)
```

> Implementation guidance: import `Recipe` at the top of `cli.py`
> (`from edge_case_engine.recipe import Recipe`). The dynamic `__import__` above is a readability
> stand-in — replace with a normal top-level `from type_handlers.resolver import TypeResolver` import.
> Keep the existing dedup/export tail of `run_fuzzer` working by passing the crash list from
> `corpus.load_crashes_v2()` (decode `input`) into the existing `CrashDeduplicator`/`PytestExporter`
> path, or guard it so the function returns cleanly when no crashes are found.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py::test_run_fuzzer_is_deterministic_with_seed -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/executor.py synthedge/cli.py type_handlers/registry.py tests/test_cli.py
git commit -m "feat: seedable run_fuzzer wired to generation engine + artifacts"
```

---

### Task 18: Architecture Gate fixture (Definition of Done)

**Files:**
- Create: `tests/test_architecture_gate.py`
- Test: same file

**Interfaces:**
- Consumes: resolver, engine, recipe replay, corpus.
- Produces: the DoD test asserting the §9 gate on a real nested-typed fixture.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_architecture_gate.py
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
    assert r.fallback_rate() == 0.0          # < 10% gate, here exactly 0

def test_deterministic_generation_and_replay():
    engine = EdgeCaseEngine()
    handlers = [TypeResolver.resolve(a) for a in FIXTURE]
    seeds = engine.generate_seeds(handlers, random.Random(2026), GenerationBudget(), n_random=10)
    # corpus replay: every recipe replays to its input
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
    assert count(value) <= 200    # bounded; accountant prevents blowup
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_architecture_gate.py -v`
Expected: FAIL only if an earlier task is incomplete; otherwise it should pass once Tasks 1–17 are in.

- [ ] **Step 3: Write minimal implementation**

No new implementation — this task validates the assembled system. If a sub-assertion fails, fix the
responsible module from Tasks 1–17 (do not weaken the gate).

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -v`
Expected: PASS (all tests green), confirming the §9 Architecture Gate:
deterministic generation, deterministic mutation (Task 13/17), corpus replay (Task 16),
crash replay (recipe lineage, Task 14), nested recursion, no exponential blow-up, fallback < 10%.

- [ ] **Step 5: Commit**

```bash
git add tests/test_architecture_gate.py
git commit -m "test: architecture-gate DoD on nested typed fixture"
```

---

## Self-Review

**Spec coverage:**
- §3 components → Tasks 1 (budget), 2 (rng), 3 (codec), 4–9 (handlers), 10 (resolver), 11/14 (recipe+replay), 12/13 (mutators), 15 (engine), 16 (corpus). ✓
- §4 interfaces → each frozen signature appears in the corresponding task's Interfaces block. ✓
- §6 invariants → H1 (Tasks 4/5 determinism tests), H2/B1 (Task 8/9/18 budget tests), H3 (edge_cases laziness, Tasks 4/8), H4 (Task 10 descriptor round-trip), H5 (Task 3 codec), R1/R2 (Task 2 + fixed traversal in composites), M1 (Tasks 12/13 record ops), P1/P2 (Tasks 14/16 replay + integrity). ✓
- §7 handler set → Tasks 4–9. ✓
- §9 DoD gate → Task 18. ✓
- §10 migration → Tasks 15 (engine), 16 (corpus), 17 (executor/cli/registry shim). ✓

**Deferred (explicit, with spec references):**
- R-2 nested-path mutation / `RecursiveMutator`: deferred to a later slice; mutation applied at root
  (`path == []`). Noted in Task 14. The DoD's "mutation coverage" is met by list+dict root mutators.
- R-4 cross-parameter combination bound: Task 15 uses `n_random` sampled combinations only (no full
  product), satisfying the "no blow-up" intent; edge-case combination expansion is left for a later slice.

**Placeholder scan:** No "TBD/TODO". Three explicit stand-ins are flagged with correction notes
(emoji literals in Task 5, newline char in Task 16, dynamic import + `__import__` in Task 17) — each
says exactly what to substitute. These are typographic escapes, not logic gaps.

**Type consistency:** `Recipe(descriptor, seed, budget, lineage)`, `LineageOp(op, path, args)`,
`generate(rng, budget)`, `mutate(handler, value, rng, budget, path) -> (value, LineageOp)`,
`materialize(recipe)`, `make_envelope(recipe, input_value, artifacts)` are used identically across all
tasks. ✓

---

## Notes for the implementer

- Run `python -m pytest` after each task; never proceed on red.
- The legacy `main.py` and `mutation_engine.py` are intentionally untouched; do not delete them in
  this slice.
- If `python --version` is < 3.9 in your shell, switch interpreters first — `typing.get_origin`
  behavior on `list[int]` (PEP 585) requires 3.9+.
