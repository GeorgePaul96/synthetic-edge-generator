# Engine Slice 2 (Deep Mutation + Generics) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make synthedge's mutation reach inside nested values and across all parameters, with live mutation and replay sharing one code path, and add `set`/`tuple`/`Literal` support.

**Architecture:** Mutators emit a single `LineageOp` (a concrete, path-addressed effect); the engine derives the mutated value by applying that op through the same `apply_lineage_op` used in replay. A `PathNavigator` selects a sub-node at any depth (descending list/dict, unwrapping Optional/Union); the engine mutates a randomly chosen parameter per iteration.

**Tech Stack:** Python 3.9+ (stdlib only), pytest. No new runtime dependencies.

## Global Constraints

- Python **3.9+**, **stdlib only** for the engine core.
- All generation/mutation **deterministic given a seed**.
- **One mutation-application implementation**: live mutation == `apply_lineage_op(base, op)` (spec §2, M1′).
- Mutators **return a `LineageOp`** (no `new_value`).
- Nested descent traverses **list and dict only**; `set`/`tuple`/scalar/`Literal` are **leaf** sites.
- Test interpreter: `python3.14 -m pytest` (3.9+ with pytest installed). All 105 existing tests stay green.
- Reference spec: `docs/superpowers/specs/2026-06-30-engine-slice2-deep-mutation-design.md`.
- Use `codec.values_equal` (not `==`) for any equality involving generated values (nan).
- Commit after every task.

---

## File Structure

New files:
- `edge_case_engine/navigator.py` — `PathNavigator`, `effective_handler`
- `type_handlers/set_handler.py` — `SetHandler`
- `type_handlers/tuple_handler.py` — `TupleHandler`
- `type_handlers/literal_handler.py` — `LiteralHandler`
- `tests/test_navigator.py`, `tests/test_generics_handlers.py`, `tests/test_nested_mutation.py`

Modified files:
- `edge_case_engine/recipe.py` — generalized `_get_node`/`_set_node`/`_compute_op`; nested `apply_lineage_op`
- `edge_case_engine/mutators/{base,scalar,collection}.py` — `mutate(...)` returns `LineageOp` only
- `edge_case_engine/engine.py` — `PathNavigator` + `mutate_step(...)`
- `synthedge/cli.py` — `run_fuzzer` uses `engine.mutate_step`
- `type_handlers/resolver.py` — `set`/`tuple`/`Literal` resolution + `from_descriptor`
- `tests/test_mutators.py` — adapt to op-only return
- `tests/test_resolver.py` — set/tuple/Literal cases
- `tests/test_architecture_gate.py` — Gate v2 cases

---

### Task 1: Generalized paths in recipe.py

**Files:**
- Modify: `edge_case_engine/recipe.py`
- Test: `tests/test_recipe.py` (append)

**Interfaces:**
- Consumes: `codec.decode` (existing), `LineageOp` (existing).
- Produces: `_get_node(root, path)`, `_set_node(root, path, new_node)`, `_compute_op(op, old_node)`;
  `apply_lineage_op(root, op)` now supports non-empty `path` (segments `["list", i]` / `["dict", encoded_key]`). Root path `[]` behaves exactly as in Slice 1.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recipe.py  (append)
from edge_case_engine.recipe import _get_node, _set_node

def test_nested_dict_add_key():
    root = [{"a": 1}, {"b": 2}]
    op = LineageOp("dict.add_key", [["list", 1]], {"key": encode("c"), "value": encode(9)})
    out = apply_lineage_op(root, op)
    assert out == [{"a": 1}, {"b": 2, "c": 9}]

def test_nested_scalar_replace():
    root = {"x": [10, 20]}
    op = LineageOp("scalar.replace", [["dict", encode("x")], ["list", 0]], {"value": encode(None)})
    out = apply_lineage_op(root, op)
    assert out == {"x": [None, 20]}

def test_get_set_node_roundtrip():
    root = [{"k": [1, 2]}]
    assert _get_node(root, [["list", 0], ["dict", encode("k")], ["list", 1]]) == 2
    _set_node(root, [["list", 0], ["dict", encode("k")], ["list", 1]], 99)
    assert root == [{"k": [1, 99]}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_recipe.py::test_nested_dict_add_key -v`
Expected: FAIL with `ImportError: cannot import name '_get_node'`.

- [ ] **Step 3: Write minimal implementation**

Replace the existing `apply_lineage_op` in `edge_case_engine/recipe.py` with the generalized version
and add the three helpers (keep `LineageOp`, `Recipe`, `materialize_base`, `materialize` as they are):

```python
# edge_case_engine/recipe.py  — replace the apply_lineage_op definition with:

def _get_node(root, path):
    node = root
    for seg in path:
        kind, key = seg[0], seg[1]
        if kind == "list":
            node = node[key]
        else:  # "dict"
            node = node[decode(key)]
    return node


def _set_node(root, path, new_node):
    if not path:
        return new_node
    parent = _get_node(root, path[:-1])
    kind, key = path[-1][0], path[-1][1]
    if kind == "list":
        parent[key] = new_node
    else:
        parent[decode(key)] = new_node
    return root


def _compute_op(op, old_node):
    name = op.op
    args = op.args
    if name == "scalar.replace":
        return decode(args["value"])
    if name == "list.insert":
        new = list(old_node); new.insert(args["index"], decode(args["value"])); return new
    if name == "list.delete":
        new = list(old_node); del new[args["index"]]; return new
    if name == "list.duplicate":
        new = list(old_node); new.insert(args["index"], new[args["index"]]); return new
    if name == "list.reverse":
        new = list(old_node); new.reverse(); return new
    if name == "list.empty":
        return []
    if name == "dict.drop_key":
        new = dict(old_node); new.pop(decode(args["key"]), None); return new
    if name == "dict.add_key":
        new = dict(old_node); new[decode(args["key"])] = decode(args["value"]); return new
    if name == "dict.corrupt_value":
        new = dict(old_node); new[decode(args["key"])] = decode(args["value"]); return new
    raise ValueError(f"unknown lineage op {name!r}")


def apply_lineage_op(root, op):
    if not isinstance(op, LineageOp):
        op = LineageOp(**op)
    target = _get_node(root, op.path)
    return _set_node(root, op.path, _compute_op(op, target))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.14 -m pytest tests/test_recipe.py -v`
Expected: PASS (existing Slice 1 recipe tests + 3 new).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/recipe.py tests/test_recipe.py
git commit -m "feat: generalized nested-path lineage application"
```

---

### Task 2: Mutators return a LineageOp only

**Files:**
- Modify: `edge_case_engine/mutators/base.py`, `scalar.py`, `collection.py`
- Test: `tests/test_mutators.py` (replace assertions)

**Interfaces:**
- Consumes: `LineageOp`, `codec.encode`.
- Produces: `Mutator.mutate(handler, value, rng, budget, path) -> LineageOp` (no tuple). `ScalarMutator`,
  `ListMutator`, `DictMutator` all return a single `LineageOp` with `path=list(path)`.

> Note: this breaks `synthedge/cli.py` until Task 6 rewires it. `tests/test_cli*.py` will be red in
> between — that is expected; run only the task's own test file until Task 6.

- [ ] **Step 1: Update the test to the op-only contract**

```python
# tests/test_mutators.py  — replace the three test bodies with:
import random
from edge_case_engine.budget import GenerationBudget
from edge_case_engine.recipe import LineageOp
from edge_case_engine.mutators.scalar import ScalarMutator
from edge_case_engine.mutators.collection import ListMutator, DictMutator
from type_handlers.scalars import IntegerHandler, StringHandler
from type_handlers.list_handler import ListHandler
from type_handlers.dict_handler import DictHandler


def test_scalar_mutator_returns_lineage_op():
    op = ScalarMutator().mutate(IntegerHandler(), 5, random.Random(2), GenerationBudget(), path=[])
    assert isinstance(op, LineageOp) and op.op == "scalar.replace" and op.path == []
    assert "value" in op.args


def test_list_mutator_returns_lineage_op_with_path():
    op = ListMutator().mutate(ListHandler(IntegerHandler()), [1, 2, 3],
                              random.Random(4), GenerationBudget(), path=[["list", 0]])
    assert isinstance(op, LineageOp) and op.op.startswith("list.") and op.path == [["list", 0]]


def test_dict_mutator_returns_lineage_op():
    op = DictMutator().mutate(DictHandler(StringHandler(), IntegerHandler()), {"a": 1},
                              random.Random(4), GenerationBudget(), path=[])
    assert isinstance(op, LineageOp) and op.op.startswith("dict.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_mutators.py -v`
Expected: FAIL (mutators currently return a tuple, so `isinstance(op, LineageOp)` is False).

- [ ] **Step 3: Update the mutators**

```python
# edge_case_engine/mutators/base.py
class Mutator:
    def can_mutate(self, handler, value) -> bool:
        raise NotImplementedError

    def mutate(self, handler, value, rng, budget, path):
        """Return a LineageOp (concrete, encoded effect at `path`). No value is returned;
        the engine derives the value by applying the op via recipe.apply_lineage_op."""
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
        return LineageOp(op="scalar.replace", path=list(path), args={"value": encode(new_value)})
```

```python
# edge_case_engine/mutators/collection.py
from edge_case_engine.mutators.base import Mutator
from edge_case_engine.recipe import LineageOp
from edge_case_engine.codec import encode


class ListMutator(Mutator):
    def can_mutate(self, handler, value) -> bool:
        return isinstance(value, list)

    def mutate(self, handler, value, rng, budget, path):
        op = rng.choice(["insert", "delete", "duplicate", "reverse", "empty"])
        args = {}
        elem_handler = getattr(handler, "elem", None)
        if op == "insert":
            idx = rng.randint(0, len(value))
            elem = elem_handler.generate(rng, budget.child()) if elem_handler else rng.randint(-1, 1)
            args = {"index": idx, "value": encode(elem)}
        elif op == "delete" and value:
            args = {"index": rng.randrange(len(value))}
        elif op == "duplicate" and value:
            args = {"index": rng.randrange(len(value))}
        elif op == "reverse":
            pass
        elif op == "empty":
            pass
        else:  # delete/duplicate on an empty list -> insert None at 0
            op = "insert"
            args = {"index": 0, "value": encode(None)}
        return LineageOp(op=f"list.{op}", path=list(path), args=args)


class DictMutator(Mutator):
    def can_mutate(self, handler, value) -> bool:
        return isinstance(value, dict)

    def mutate(self, handler, value, rng, budget, path):
        key_handler = getattr(handler, "key", None)
        val_handler = getattr(handler, "val", None)
        op = rng.choice(["drop_key", "add_key", "corrupt_value"])
        args = {}
        keys = list(value.keys())
        if op == "drop_key" and keys:
            args = {"key": encode(rng.choice(keys))}
        elif op == "add_key":
            k = key_handler.generate(rng, budget.child()) if key_handler else "k"
            v = val_handler.generate(rng, budget.child()) if val_handler else 0
            args = {"key": encode(k), "value": encode(v)}
        elif op == "corrupt_value" and keys:
            corrupt = rng.choice([None, "synthedge", float("nan")])
            args = {"key": encode(rng.choice(keys)), "value": encode(corrupt)}
        else:  # drop/corrupt on an empty dict -> add a key
            op = "add_key"
            args = {"key": encode("synthedge"), "value": encode(None)}
        return LineageOp(op=f"dict.{op}", path=list(path), args=args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_mutators.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/mutators tests/test_mutators.py
git commit -m "refactor: mutators emit a single LineageOp (no new_value)"
```

---

### Task 3: Set/Tuple/Literal handlers

**Files:**
- Create: `type_handlers/set_handler.py`, `type_handlers/tuple_handler.py`, `type_handlers/literal_handler.py`
- Test: `tests/test_generics_handlers.py`

**Interfaces:**
- Consumes: `Handler` (existing), `GenerationBudget`, `codec.encode`.
- Produces:
  - `SetHandler(elem)` — `.elem`; `type_sig "set[X]"`; `descriptor {"k":"set","elem":…}`.
  - `TupleHandler(elems, variadic=False)` — `.elems`, `.variadic`; fixed `tuple[A,B]` / variadic
    `tuple[A,...]`; `descriptor {"k":"tuple","elems":[…],"variadic":bool}`.
  - `LiteralHandler(values)` — `.values`; `descriptor {"k":"literal","values":[encoded…]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generics_handlers.py
import random
from edge_case_engine.budget import GenerationBudget
from type_handlers.scalars import IntegerHandler, StringHandler
from type_handlers.set_handler import SetHandler
from type_handlers.tuple_handler import TupleHandler
from type_handlers.literal_handler import LiteralHandler


def test_set_handler_generates_set_deterministically():
    h = SetHandler(IntegerHandler())
    b = GenerationBudget(max_list_length=4, max_total_nodes=50)
    v1 = h.generate(random.Random(5), GenerationBudget(max_list_length=4, max_total_nodes=50))
    v2 = h.generate(random.Random(5), b)
    assert isinstance(v1, set) and v1 == v2
    assert h.type_sig() == "set[int]"
    assert h.descriptor() == {"k": "set", "elem": {"k": "int"}}


def test_tuple_fixed_and_variadic():
    fixed = TupleHandler([IntegerHandler(), StringHandler()], variadic=False)
    v = fixed.generate(random.Random(1), GenerationBudget())
    assert isinstance(v, tuple) and len(v) == 2
    assert fixed.type_sig() == "tuple[int, str]"
    var = TupleHandler([IntegerHandler()], variadic=True)
    assert var.type_sig() == "tuple[int, ...]"
    assert isinstance(var.generate(random.Random(1), GenerationBudget()), tuple)


def test_literal_handler_picks_from_values():
    h = LiteralHandler(["a", "b", "c"])
    assert h.generate(random.Random(0), GenerationBudget()) in {"a", "b", "c"}
    assert list(h.edge_cases()) == ["a", "b", "c"]
    assert h.descriptor()["k"] == "literal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_generics_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError: type_handlers.set_handler`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/set_handler.py
from type_handlers.base import Handler


class SetHandler(Handler):
    def __init__(self, elem):
        self.elem = elem

    def generate(self, rng, budget):
        if budget.depth_exhausted():
            return set()
        n = rng.randint(0, budget.max_list_length)
        child = budget.child()
        out = set()
        for _ in range(n):
            if not budget.spend(1):
                break
            v = self.elem.generate(rng, child)
            try:
                out.add(v)
            except TypeError:
                continue  # unhashable generated element
        return out

    def edge_cases(self):
        yield set()
        for v in self.elem.edge_cases():
            try:
                s = {v}
            except TypeError:
                continue
            yield s

    def type_sig(self):
        return f"set[{self.elem.type_sig()}]"

    def descriptor(self):
        return {"k": "set", "elem": self.elem.descriptor()}
```

```python
# type_handlers/tuple_handler.py
from type_handlers.base import Handler


class TupleHandler(Handler):
    def __init__(self, elems, variadic=False):
        self.elems = list(elems)
        self.variadic = variadic

    def generate(self, rng, budget):
        if self.variadic:
            if budget.depth_exhausted():
                return ()
            n = rng.randint(0, budget.max_list_length)
            child = budget.child()
            out = []
            for _ in range(n):
                if not budget.spend(1):
                    break
                out.append(self.elems[0].generate(rng, child))
            return tuple(out)
        child = budget.child()
        return tuple(e.generate(rng, child) for e in self.elems)

    def edge_cases(self):
        if self.variadic:
            yield ()
            for v in self.elems[0].edge_cases():
                yield (v,)
        else:
            yield tuple(next(e.edge_cases()) for e in self.elems)

    def type_sig(self):
        if self.variadic:
            return f"tuple[{self.elems[0].type_sig()}, ...]"
        return "tuple[" + ", ".join(e.type_sig() for e in self.elems) + "]"

    def descriptor(self):
        return {"k": "tuple", "elems": [e.descriptor() for e in self.elems], "variadic": self.variadic}
```

```python
# type_handlers/literal_handler.py
from type_handlers.base import Handler
from edge_case_engine.codec import encode


class LiteralHandler(Handler):
    def __init__(self, values):
        self.values = list(values)

    def generate(self, rng, budget):
        return rng.choice(self.values)

    def edge_cases(self):
        for v in self.values:
            yield v

    def type_sig(self):
        return "Literal[" + ", ".join(repr(v) for v in self.values) + "]"

    def descriptor(self):
        return {"k": "literal", "values": [encode(v) for v in self.values]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_generics_handlers.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/set_handler.py type_handlers/tuple_handler.py type_handlers/literal_handler.py tests/test_generics_handlers.py
git commit -m "feat: add Set/Tuple/Literal handlers"
```

---

### Task 4: Resolver wiring for set/tuple/Literal

**Files:**
- Modify: `type_handlers/resolver.py`
- Test: `tests/test_resolver.py` (append)

**Interfaces:**
- Consumes: `SetHandler`, `TupleHandler`, `LiteralHandler` (Task 3), `codec.decode`.
- Produces: `TypeResolver.resolve` handles `set[X]`, `tuple[...]` (fixed + variadic), `typing.Literal`;
  `from_descriptor` handles `set`/`tuple`/`literal`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resolver.py  (append)
from typing import Set, Tuple, Literal

def test_resolves_set_tuple_literal():
    assert TypeResolver.resolve(Set[int]).type_sig() == "set[int]"
    assert TypeResolver.resolve(Tuple[int, str]).type_sig() == "tuple[int, str]"
    assert TypeResolver.resolve(Tuple[int, ...]).type_sig() == "tuple[int, ...]"
    assert TypeResolver.resolve(Literal["a", "b"]).type_sig() == "Literal['a', 'b']"

def test_set_tuple_literal_descriptor_roundtrip():
    for ann in [Set[int], Tuple[int, str], Tuple[int, ...], Literal[1, 2, 3]]:
        h = TypeResolver.resolve(ann)
        assert TypeResolver.from_descriptor(h.descriptor()).type_sig() == h.type_sig()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_resolver.py::test_resolves_set_tuple_literal -v`
Expected: FAIL (set resolves to `FloatHandler` fallback, so `type_sig` != `"set[int]"`).

- [ ] **Step 3: Update the resolver**

Add imports at the top of `type_handlers/resolver.py`:

```python
from type_handlers.set_handler import SetHandler
from type_handlers.tuple_handler import TupleHandler
from type_handlers.literal_handler import LiteralHandler
from edge_case_engine.codec import decode as _decode
```

In `resolve`, add these branches **before** the final "unknown annotation" fallback (after the existing
`Union` branch):

```python
        if origin is set:
            return SetHandler(cls.resolve(args[0], strict) if args else FloatHandler())
        if origin is tuple:
            if not args:
                return TupleHandler([FloatHandler()], variadic=True)
            if len(args) == 2 and args[1] is Ellipsis:
                return TupleHandler([cls.resolve(args[0], strict)], variadic=True)
            return TupleHandler([cls.resolve(a, strict) for a in args], variadic=False)
        if origin is typing.Literal:
            return LiteralHandler(list(args))
```

In `from_descriptor`, add these cases (before the final `raise`):

```python
        if k == "set":
            return SetHandler(cls.from_descriptor(desc["elem"]))
        if k == "tuple":
            return TupleHandler([cls.from_descriptor(e) for e in desc["elems"]],
                                variadic=desc["variadic"])
        if k == "literal":
            return LiteralHandler([_decode(v) for v in desc["values"]])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_resolver.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/resolver.py tests/test_resolver.py
git commit -m "feat: resolve set/tuple/Literal to handlers"
```

---

### Task 5: PathNavigator + effective_handler

**Files:**
- Create: `edge_case_engine/navigator.py`
- Test: `tests/test_navigator.py`

**Interfaces:**
- Consumes: all handler classes, `codec.encode`, `recipe._get_node` (for the soundness test).
- Produces: `effective_handler(handler, value) -> Handler` (unwraps Optional/Union to match the runtime
  value); `PathNavigator(stop_prob=0.5).select(handler, value, rng) -> (path, sub_handler, sub_value)`
  where `path` is a list of `["list", i]` / `["dict", encoded_key]` segments and
  `_get_node(value, path) == sub_value`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_navigator.py
import random
from typing import List, Dict, Optional
from type_handlers.resolver import TypeResolver
from type_handlers.scalars import IntegerHandler
from type_handlers.optional_handler import OptionalHandler
from edge_case_engine.navigator import PathNavigator, effective_handler
from edge_case_engine.recipe import _get_node


def test_effective_handler_unwraps_optional():
    h = TypeResolver.resolve(Optional[int])
    assert isinstance(effective_handler(h, 5), IntegerHandler)
    assert isinstance(effective_handler(h, None), OptionalHandler)


def test_navigator_path_is_sound():
    h = TypeResolver.resolve(List[Dict[str, int]])
    value = [{"a": 1, "b": 2}, {"c": 3}]
    nav = PathNavigator(stop_prob=0.0)   # descend all the way to a leaf
    for s in range(50):
        path, sub_h, sub_v = nav.select(h, value, random.Random(s))
        assert _get_node(value, path) == sub_v


def test_navigator_leaf_on_scalar():
    h = IntegerHandler()
    path, sub_h, sub_v = PathNavigator().select(h, 7, random.Random(0))
    assert path == [] and sub_v == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_navigator.py -v`
Expected: FAIL with `ModuleNotFoundError: edge_case_engine.navigator`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/navigator.py
from edge_case_engine.codec import encode
from type_handlers.scalars import (
    FloatHandler, IntegerHandler, StringHandler, BoolHandler, NoneHandler,
)
from type_handlers.list_handler import ListHandler
from type_handlers.dict_handler import DictHandler
from type_handlers.optional_handler import OptionalHandler
from type_handlers.union_handler import UnionHandler
from type_handlers.set_handler import SetHandler
from type_handlers.tuple_handler import TupleHandler
from type_handlers.literal_handler import LiteralHandler


def _matches(handler, value):
    if isinstance(handler, BoolHandler):
        return isinstance(value, bool)
    if isinstance(handler, IntegerHandler):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(handler, FloatHandler):
        return isinstance(value, float)
    if isinstance(handler, StringHandler):
        return isinstance(value, str)
    if isinstance(handler, NoneHandler):
        return value is None
    if isinstance(handler, ListHandler):
        return isinstance(value, list)
    if isinstance(handler, DictHandler):
        return isinstance(value, dict)
    if isinstance(handler, SetHandler):
        return isinstance(value, set)
    if isinstance(handler, TupleHandler):
        return isinstance(value, tuple)
    if isinstance(handler, LiteralHandler):
        return value in handler.values
    if isinstance(handler, OptionalHandler):
        return value is None or _matches(handler.inner, value)
    if isinstance(handler, UnionHandler):
        return any(_matches(o, value) for o in handler.options)
    return False


def effective_handler(handler, value):
    """Unwrap Optional/Union to the handler matching the concrete runtime value."""
    if isinstance(handler, OptionalHandler):
        return effective_handler(handler.inner, value) if value is not None else handler
    if isinstance(handler, UnionHandler):
        for opt in handler.options:
            if _matches(opt, value):
                return effective_handler(opt, value)
        return handler
    return handler


class PathNavigator:
    def __init__(self, stop_prob: float = 0.5):
        self.stop_prob = stop_prob

    def _descend_options(self, handler, value):
        opts = []
        if isinstance(handler, ListHandler) and isinstance(value, list) and value:
            for i in range(len(value)):
                opts.append((["list", i], handler.elem, value[i]))
        elif isinstance(handler, DictHandler) and isinstance(value, dict) and value:
            for k in value.keys():
                opts.append((["dict", encode(k)], handler.val, value[k]))
        return opts

    def select(self, handler, value, rng):
        path = []
        h, v = effective_handler(handler, value), value
        while True:
            options = self._descend_options(h, v)
            if not options or rng.random() < self.stop_prob:
                return path, h, v
            seg, child_h, child_v = rng.choice(options)
            path.append(seg)
            h, v = effective_handler(child_h, child_v), child_v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_navigator.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/navigator.py tests/test_navigator.py
git commit -m "feat: add PathNavigator and Optional/Union unwrapping"
```

---

### Task 6: Engine mutate_step + CLI wiring (multi-param, nested)

**Files:**
- Modify: `edge_case_engine/engine.py`, `synthedge/cli.py`
- Test: `tests/test_nested_mutation.py`

**Interfaces:**
- Consumes: `PathNavigator` (Task 5), `MutatorRegistry`, `apply_lineage_op`/`Recipe` (recipe), `copy`.
- Produces: `EdgeCaseEngine.navigator: PathNavigator`; `EdgeCaseEngine.mutate_step(handlers,
  base_input, base_recipes, rng, budget) -> (mutated_tuple, new_recipes, pi) | None`. `run_fuzzer`
  uses `mutate_step` for each iteration.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nested_mutation.py
import random
from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.budget import GenerationBudget
from type_handlers.scalars import IntegerHandler, StringHandler, FloatHandler


def test_mutate_step_covers_all_params():
    engine = EdgeCaseEngine()
    handlers = [IntegerHandler(), StringHandler(), FloatHandler()]
    budget = GenerationBudget()
    master = random.Random(7)
    seeds = engine.generate_seeds(handlers, master, budget, n_random=1)
    base_input, base_recipes = seeds[0]
    touched = set()
    for _ in range(200):
        res = engine.mutate_step(handlers, base_input, base_recipes, master, budget)
        if res is not None:
            touched.add(res[2])
    assert touched == {0, 1, 2}


def test_mutate_step_recipe_replays_to_mutated_param():
    from edge_case_engine.recipe import materialize
    from edge_case_engine.codec import values_equal
    engine = EdgeCaseEngine()
    handlers = [IntegerHandler()]
    budget = GenerationBudget()
    master = random.Random(3)
    base_input, base_recipes = engine.generate_seeds(handlers, master, budget, n_random=1)[0]
    res = engine.mutate_step(handlers, base_input, base_recipes, master, budget)
    assert res is not None
    mutated, new_recipes, pi = res
    assert values_equal(materialize(new_recipes[pi]), mutated[pi])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_nested_mutation.py -v`
Expected: FAIL with `AttributeError: 'EdgeCaseEngine' object has no attribute 'mutate_step'`.

- [ ] **Step 3: Update the engine and CLI**

```python
# edge_case_engine/engine.py  — replace the file with:
import copy
import random

from edge_case_engine.recipe import Recipe, materialize, apply_lineage_op
from edge_case_engine.mutators.registry import MutatorRegistry
from edge_case_engine.navigator import PathNavigator


class EdgeCaseEngine:
    def __init__(self):
        self.mutation = MutatorRegistry()
        self.navigator = PathNavigator()

    def _param_recipe(self, handler, master_rng, budget):
        seed = master_rng.getrandbits(64)
        return Recipe(descriptor=handler.descriptor(), seed=seed,
                      budget=budget.to_dict(), lineage=[])

    def generate_seeds(self, handlers, master_rng, budget, n_random=20):
        seeds = []
        seen = set()

        def add(recipes):
            inp = tuple(materialize(r) for r in recipes)
            key = repr(inp)
            if key in seen:
                return
            seen.add(key)
            seeds.append((inp, recipes))

        for _ in range(n_random):
            recipes = [self._param_recipe(h, master_rng, budget) for h in handlers]
            add(recipes)
        return seeds

    def mutate_step(self, handlers, base_input, base_recipes, rng, budget):
        """Mutate a randomly chosen parameter at a navigator-selected site.
        Returns (mutated_tuple, new_recipes, param_index) or None if no mutator applies."""
        pi = rng.randrange(len(handlers))
        path, h_sub, v_sub = self.navigator.select(handlers[pi], base_input[pi], rng)
        mutator = self.mutation.choose(h_sub, v_sub, rng)
        if mutator is None:
            return None
        op = mutator.mutate(h_sub, v_sub, rng, budget, path)
        new_param = apply_lineage_op(copy.deepcopy(base_input[pi]), op)
        mutated = tuple(new_param if j == pi else base_input[j] for j in range(len(base_input)))
        new_recipes = [Recipe.from_dict(r.to_dict()) for r in base_recipes]
        new_recipes[pi].lineage = list(base_recipes[pi].lineage) + [op]
        return mutated, new_recipes, pi
```

In `synthedge/cli.py`, replace the per-iteration mutation block inside `run_fuzzer` (the part that
currently picks `h0`, calls `mutator.mutate`, builds `mutated`/`new_recipes`) with a call to
`engine.mutate_step`:

```python
        for _ in range(iterations):
            if not pool:
                break
            base_input, base_recipes = pool[master_rng.randrange(len(pool))]

            step = engine.mutate_step(handlers, base_input, base_recipes, master_rng, budget)
            if step is None:
                continue
            mutated, new_recipes, pi = step

            results = executor.execute(target.function, [mutated])
            for result in results:
                exc = (None if result.error is None
                       else f"{type(result.error).__name__}: {result.error}")
                env = corpus.make_envelope(new_recipes[pi], mutated[pi],
                                           artifacts={"exception": exc,
                                                      "coverage": result.coverage_id,
                                                      "output": None})
                if result.new_path:
                    pool.append((mutated, new_recipes))
                    corpus.save_interesting(env)
                if result.error is not None:
                    corpus.save_crash(env)
                    corpus.record_crash(list(mutated), exc, result.severity)
                    crashes_found += 1
```

Remove the now-unused `Recipe` import line from `cli.py` only if it is no longer referenced; leave the
other imports (`apply_lineage_op` is not needed in `cli.py` anymore — the engine owns it).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3.14 -m pytest tests/test_nested_mutation.py tests/test_cli.py tests/test_cli_seed.py -v`
Expected: PASS (nested-mutation tests + all CLI tests green again).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/engine.py synthedge/cli.py tests/test_nested_mutation.py
git commit -m "feat: multi-parameter nested mutation via mutate_step"
```

---

### Task 7: Architecture Gate v2

**Files:**
- Modify: `tests/test_architecture_gate.py` (append)
- Test: same file

**Interfaces:**
- Consumes: resolver, engine, navigator, recipe replay, codec.
- Produces: Gate-v2 assertions (spec §8): live ≡ replay for nested mutation, navigator soundness on
  nested fixtures, generics round-trip, no fallback on the extended fixture.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_architecture_gate.py  (append)
import copy
from typing import Set, Tuple, Literal
from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.navigator import PathNavigator
from edge_case_engine.recipe import Recipe, materialize, apply_lineage_op, _get_node
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_architecture_gate.py -v`
Expected: Only the three new tests are collected as new; they should pass once Tasks 1–6 are in. If
`test_live_equals_replay_for_nested_mutation` fails on `checked > 0`, raise the seed range — but with
300 seeds nested paths occur. Investigate any `values_equal` failure as a real defect in Tasks 1/5/6.

- [ ] **Step 3: No new implementation**

This task validates the assembled system. If any assertion fails, fix the responsible module from
Tasks 1–6 (do not weaken the gate).

- [ ] **Step 4: Run the full suite**

Run: `python3.14 -m pytest -q`
Expected: PASS (all previous tests + Slice 2 tests green), confirming Gate v2: nested live ≡ replay,
navigator soundness, generics round-trip, multi-parameter coverage (Task 6).

- [ ] **Step 5: Commit**

```bash
git add tests/test_architecture_gate.py
git commit -m "test: architecture-gate v2 (nested mutation, generics, navigator soundness)"
```

---

## Self-Review

**Spec coverage:**
- §2 mutators-emit-op + single apply path → Tasks 2 (op-only) + 1/6 (single `apply_lineage_op`). ✓
- §3 generalized paths (`_get_node`/`_set_node`/`_compute_op`) → Task 1. ✓
- §4 PathNavigator + `effective_handler` (Optional/Union unwrap, list/dict descent, leaves) → Task 5. ✓
- §5 multi-parameter nested mutation flow → Task 6 (`mutate_step` + CLI). ✓
- §6 set/tuple(fixed+variadic)/Literal handlers + resolver + codec → Tasks 3, 4 (codec already supports set/tuple; Literal primitives). ✓
- §7 invariants M1′ (Task 6 + gate), P3 nested replay (Task 7), N1 navigator soundness (Tasks 5, 7), D1 deepcopy (Task 6). ✓
- §8 Architecture Gate v2 → Task 7. ✓
- §9 migration/file plan → matches Tasks 1–7. ✓

**Placeholder scan:** No "TBD/TODO". The one judgment note (raise seed range if `checked == 0`) is a
contingency, not a gap — 300 seeds reliably produce nested paths on `list[dict[str,int]]`.

**Type consistency:** `LineageOp(op, path, args)`, `mutate(handler, value, rng, budget, path) ->
LineageOp`, `_get_node(root, path)`, `_set_node(root, path, new_node)`, `_compute_op(op, old_node)`,
`apply_lineage_op(root, op)`, `PathNavigator.select(handler, value, rng) -> (path, handler, value)`,
`effective_handler(handler, value)`, `EdgeCaseEngine.mutate_step(...) -> (mutated, new_recipes, pi)` are
used identically across tasks. Segment form `["list", i]` / `["dict", encode(key)]` is consistent in
Tasks 1, 5, 6, 7. ✓

---

## Notes for the implementer

- Run `python3.14 -m pytest` (Python 3.9+ with pytest) after each task; the active shell `python` is
  3.8 and lacks pytest.
- `tests/test_cli*.py` is intentionally red between Task 2 and Task 6 (mutator contract change).
- `set`/`tuple` already round-trip through `edge_case_engine/codec.py`; no codec edits in this slice.
- Do not descend into `set`/`tuple` nodes — they are leaves (mutated whole by `ScalarMutator`).
