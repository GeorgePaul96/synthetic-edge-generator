# Engine Slice 3 (User-Defined Types: Enum + dataclass) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fuzz functions whose parameters are `Enum` subclasses or `@dataclass` types, with full replay across runs.

**Architecture:** A `classref` helper references user classes by `module:qualname`; the codec gains enum/dataclass tags (with a nan-aware `values_equal` dataclass branch); `EnumHandler`/`DataclassHandler` generate instances and the resolver detects these annotations. Enum/dataclass values are leaf mutation sites, so the mutation engine is untouched.

**Tech Stack:** Python 3.9+ (stdlib only: `enum`, `dataclasses`, `importlib`, `typing`), pytest.

## Global Constraints

- Python **3.9+**, **stdlib only**. No Pydantic (deferred to Slice 4).
- All generation **deterministic given a seed**; recipes replay to `values_equal` values.
- Enum/dataclass are **leaf** mutation sites — no navigator/path/mutator changes.
- The **enum `encode` branch precedes int/float/str** (an `IntEnum` member is also an `int`).
- Test interpreter: `python3.14 -m pytest` (Python 3.9+ with pytest). All 121 existing tests stay green.
- Use `codec.values_equal` (not `==`) for equality involving generated values.
- Reference spec: `docs/superpowers/specs/2026-06-30-engine-slice3-user-types-design.md`.
- Commit after every task.

---

## File Structure

New files:
- `edge_case_engine/classref.py` — `class_to_ref`, `ref_to_class`
- `type_handlers/enum_handler.py` — `EnumHandler`
- `type_handlers/dataclass_handler.py` — `DataclassHandler`
- `tests/user_type_fixtures.py` — importable `Color`/`Priority`/`Point`/`Box` fixtures (not a test module)
- `tests/test_classref.py`, `tests/test_user_type_codec.py`, `tests/test_user_type_handlers.py`

Modified files:
- `edge_case_engine/codec.py` — enum/dataclass `encode`/`decode` + `values_equal` dataclass branch
- `type_handlers/resolver.py` — Enum/dataclass detection + `from_descriptor` cases
- `synthedge/cli.py` — `load_module_from_path` stable module naming (round-trippable class refs)
- `tests/test_architecture_gate.py` — Gate v3 cases

---

### Task 1: classref helper + fixtures

**Files:**
- Create: `edge_case_engine/classref.py`, `tests/user_type_fixtures.py`
- Test: `tests/test_classref.py`

**Interfaces:**
- Consumes: `importlib` (stdlib).
- Produces: `class_to_ref(cls) -> str` (`"module:Qualname"`), `ref_to_class(ref) -> cls`. Fixtures
  module exposes `Color(enum.Enum)`, `Priority(enum.IntEnum)`, `Point` dataclass `(x:int, y:int)`,
  `Box` dataclass `(label:str, size:float, tag:Optional[Color])`.

- [ ] **Step 1: Write the failing test**

```python
# tests/user_type_fixtures.py
import enum
from dataclasses import dataclass
from typing import Optional


class Color(enum.Enum):
    RED = 1
    GREEN = 2
    BLUE = 3


class Priority(enum.IntEnum):
    LOW = 1
    HIGH = 2


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Box:
    label: str
    size: float
    tag: Optional[Color]
```

```python
# tests/test_classref.py
from tests.user_type_fixtures import Color, Priority, Point, Box
from edge_case_engine.classref import class_to_ref, ref_to_class


def test_class_ref_roundtrip():
    for C in (Color, Priority, Point, Box):
        ref = class_to_ref(C)
        assert ":" in ref
        assert ref_to_class(ref) is C
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_classref.py -v`
Expected: FAIL with `ModuleNotFoundError: edge_case_engine.classref`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/classref.py
import importlib


def class_to_ref(cls) -> str:
    """Stable reference to an importable class: 'package.module:Outer.Inner'."""
    return f"{cls.__module__}:{cls.__qualname__}"


def ref_to_class(ref: str):
    """Resolve a 'module:qualname' reference back to the class object."""
    module, qual = ref.split(":", 1)
    obj = importlib.import_module(module)
    for part in qual.split("."):
        obj = getattr(obj, part)
    return obj
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_classref.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/classref.py tests/user_type_fixtures.py tests/test_classref.py
git commit -m "feat: add class-identity reference helper + user-type fixtures"
```

---

### Task 2: Codec enum/dataclass tags + values_equal dataclass branch

**Files:**
- Modify: `edge_case_engine/codec.py`
- Test: `tests/test_user_type_codec.py`

**Interfaces:**
- Consumes: `classref.class_to_ref`/`ref_to_class`, `enum`, `dataclasses`.
- Produces: `encode`/`decode` round-trip enum members (`{"$t":"enum",...}`) and dataclass instances
  (`{"$t":"dataclass",...}`); `values_equal` compares dataclass instances field-wise (nan-aware).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_user_type_codec.py
import math
from edge_case_engine.codec import encode, decode, values_equal
from tests.user_type_fixtures import Color, Priority, Point, Box


def test_enum_member_roundtrip():
    assert values_equal(decode(encode(Color.GREEN)), Color.GREEN)
    assert decode(encode(Priority.HIGH)) is Priority.HIGH   # IntEnum, encoded as enum not int


def test_dataclass_roundtrip_including_nan_field():
    box = Box(label="x", size=float("nan"), tag=Color.RED)
    restored = decode(encode(box))
    assert values_equal(restored, box)          # nan-aware dataclass equality
    assert math.isnan(restored.size)
    assert restored.tag is Color.RED


def test_values_equal_dataclass_distinguishes_fields():
    assert values_equal(Point(1, 2), Point(1, 2)) is True
    assert values_equal(Point(1, 2), Point(1, 3)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_user_type_codec.py -v`
Expected: FAIL — `encode(Color.GREEN)` raises `TypeError: codec cannot encode <enum 'Color'>`.

- [ ] **Step 3: Update the codec**

Add imports at the top of `edge_case_engine/codec.py`:

```python
import enum
import dataclasses
from edge_case_engine.classref import class_to_ref, ref_to_class
```

Replace `encode` with (enum check first; dataclass before the final `raise`):

```python
def encode(value):
    if isinstance(value, enum.Enum):                       # before int/float/str (IntEnum/StrEnum)
        return {"$t": "enum", "$v": [class_to_ref(type(value)), value.name]}
    if isinstance(value, bool):
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
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"$t": "dataclass", "$v": [
            class_to_ref(type(value)),
            {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)},
        ]}
    raise TypeError(f"codec cannot encode {type(value)!r}")
```

Add two branches inside `decode` (alongside the existing tag handling):

```python
        if t == "enum":
            ref, name = obj["$v"]
            return ref_to_class(ref)[name]
        if t == "dataclass":
            ref, field_map = obj["$v"]
            cls = ref_to_class(ref)
            return cls(**{k: decode(v) for k, v in field_map.items()})
```

Add a dataclass branch in `values_equal`, immediately before the final `return a == b`:

```python
    if dataclasses.is_dataclass(a) and not isinstance(a, type):
        return all(values_equal(getattr(a, f.name), getattr(b, f.name))
                   for f in dataclasses.fields(a))
    return a == b
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_user_type_codec.py tests/test_codec.py -v`
Expected: PASS (new user-type codec tests + existing codec tests).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/codec.py tests/test_user_type_codec.py
git commit -m "feat: codec enum/dataclass tags with nan-aware dataclass equality"
```

---

### Task 3: EnumHandler + DataclassHandler

**Files:**
- Create: `type_handlers/enum_handler.py`, `type_handlers/dataclass_handler.py`
- Test: `tests/test_user_type_handlers.py`

**Interfaces:**
- Consumes: `Handler`, `GenerationBudget`, `classref.class_to_ref`.
- Produces:
  - `EnumHandler(enum_cls)` — `.enum_cls`, `.members`; `type_sig "Enum[<Qual>]"`;
    `descriptor {"k":"enum","cls":ref}`.
  - `DataclassHandler(cls, fields)` — `.cls`, `.fields` (ordered `{name: Handler}`);
    `generate` constructs `cls(**{name: handler.generate(...)})`; `type_sig "dataclass[<Qual>]"`;
    `descriptor {"k":"dataclass","cls":ref,"fields":{name: child_desc}}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_user_type_handlers.py
import random
from edge_case_engine.budget import GenerationBudget
from edge_case_engine.codec import values_equal
from type_handlers.enum_handler import EnumHandler
from type_handlers.dataclass_handler import DataclassHandler
from type_handlers.scalars import IntegerHandler
from tests.user_type_fixtures import Color, Point


def test_enum_handler_generates_member_deterministically():
    h = EnumHandler(Color)
    b = GenerationBudget()
    assert h.generate(random.Random(1), b) is h.generate(random.Random(1), b)
    assert h.generate(random.Random(1), b) in list(Color)
    assert h.descriptor() == {"k": "enum", "cls": "tests.user_type_fixtures:Color"}


def test_dataclass_handler_constructs_instance():
    h = DataclassHandler(Point, {"x": IntegerHandler(), "y": IntegerHandler()})
    b = GenerationBudget()
    v1 = h.generate(random.Random(2), b)
    v2 = h.generate(random.Random(2), GenerationBudget())
    assert isinstance(v1, Point) and values_equal(v1, v2)
    assert h.type_sig() == "dataclass[Point]"
    assert h.descriptor()["k"] == "dataclass" and "x" in h.descriptor()["fields"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_user_type_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError: type_handlers.enum_handler`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/enum_handler.py
from type_handlers.base import Handler
from edge_case_engine.classref import class_to_ref


class EnumHandler(Handler):
    def __init__(self, enum_cls):
        self.enum_cls = enum_cls
        self.members = list(enum_cls)

    def generate(self, rng, budget):
        return rng.choice(self.members)

    def edge_cases(self):
        for m in self.members:
            yield m

    def type_sig(self):
        return f"Enum[{self.enum_cls.__qualname__}]"

    def descriptor(self):
        return {"k": "enum", "cls": class_to_ref(self.enum_cls)}
```

```python
# type_handlers/dataclass_handler.py
from type_handlers.base import Handler
from edge_case_engine.classref import class_to_ref


class DataclassHandler(Handler):
    def __init__(self, cls, fields):
        self.cls = cls
        self.fields = fields            # ordered dict {name: Handler}

    def generate(self, rng, budget):
        child = budget.child()
        budget.spend(1)
        kwargs = {name: h.generate(rng, child) for name, h in self.fields.items()}
        return self.cls(**kwargs)

    def edge_cases(self):
        yield self.cls(**{name: next(h.edge_cases()) for name, h in self.fields.items()})

    def type_sig(self):
        return f"dataclass[{self.cls.__qualname__}]"

    def descriptor(self):
        return {"k": "dataclass", "cls": class_to_ref(self.cls),
                "fields": {n: h.descriptor() for n, h in self.fields.items()}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_user_type_handlers.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/enum_handler.py type_handlers/dataclass_handler.py tests/test_user_type_handlers.py
git commit -m "feat: add EnumHandler and DataclassHandler"
```

---

### Task 4: Resolver detection + from_descriptor

**Files:**
- Modify: `type_handlers/resolver.py`
- Test: `tests/test_resolver.py` (append)

**Interfaces:**
- Consumes: `EnumHandler`, `DataclassHandler`, `classref.ref_to_class`, `enum`, `dataclasses`.
- Produces: `TypeResolver.resolve` maps `Enum` subclasses → `EnumHandler` and dataclasses →
  `DataclassHandler` (resolving each field via `get_type_hints`, with graceful fallback on failure);
  `from_descriptor` handles `enum`/`dataclass`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resolver.py  (append)
def test_resolves_enum_and_dataclass():
    from tests.user_type_fixtures import Color, Box
    from type_handlers.enum_handler import EnumHandler
    from type_handlers.dataclass_handler import DataclassHandler
    assert isinstance(TypeResolver.resolve(Color), EnumHandler)
    h = TypeResolver.resolve(Box)
    assert isinstance(h, DataclassHandler)
    assert set(h.fields.keys()) == {"label", "size", "tag"}
    # descriptor round-trip rebuilds an equivalent handler
    assert TypeResolver.from_descriptor(h.descriptor()).type_sig() == h.type_sig()
    assert TypeResolver.from_descriptor(TypeResolver.resolve(Color).descriptor()).type_sig() == "Enum[Color]"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_resolver.py::test_resolves_enum_and_dataclass -v`
Expected: FAIL (`Color` currently resolves to the `FloatHandler` fallback).

- [ ] **Step 3: Update the resolver**

Add imports at the top of `type_handlers/resolver.py`:

```python
import enum
import dataclasses
from type_handlers.enum_handler import EnumHandler
from type_handlers.dataclass_handler import DataclassHandler
from edge_case_engine.classref import ref_to_class
```

In `resolve`, add these branches **before** the final "unknown annotation" fallback (after the
`Literal` branch):

```python
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            return EnumHandler(annotation)
        if dataclasses.is_dataclass(annotation) and isinstance(annotation, type):
            try:
                hints = typing.get_type_hints(annotation)
            except Exception:
                if strict:
                    raise
                _FallbackCounter.count += 1
                return FloatHandler()
            fields = {f.name: cls.resolve(hints.get(f.name, None), strict)
                      for f in dataclasses.fields(annotation)}
            return DataclassHandler(annotation, fields)
```

In `from_descriptor`, add these cases (before the final `raise`):

```python
        if k == "enum":
            return EnumHandler(ref_to_class(desc["cls"]))
        if k == "dataclass":
            cls_obj = ref_to_class(desc["cls"])
            fields = {n: cls.from_descriptor(d) for n, d in desc["fields"].items()}
            return DataclassHandler(cls_obj, fields)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_resolver.py -v`
Expected: PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add type_handlers/resolver.py tests/test_resolver.py
git commit -m "feat: resolve Enum and dataclass annotations to handlers"
```

---

### Task 5: Round-trippable dynamic target modules

**Files:**
- Modify: `synthedge/cli.py` (`load_module_from_path`)
- Test: `tests/test_user_type_handlers.py` (append)

**Interfaces:**
- Consumes: `importlib`, `classref`.
- Produces: `load_module_from_path` registers the loaded module in `sys.modules` under a **stable name
  equal to the module's `__name__`**, so classes defined in a dynamically-loaded target file are
  importable via `ref_to_class` (round-trippable class refs).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_user_type_handlers.py  (append)
def test_dynamic_module_class_is_ref_roundtrippable(tmp_path):
    from synthedge.cli import load_module_from_path
    from edge_case_engine.classref import class_to_ref, ref_to_class
    target = tmp_path / "tgt.py"
    target.write_text("from dataclasses import dataclass\n@dataclass\nclass Q:\n    a: int\n")
    module = load_module_from_path(str(target))
    Q = module.Q
    assert ref_to_class(class_to_ref(Q)) is Q
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_user_type_handlers.py::test_dynamic_module_class_is_ref_roundtrippable -v`
Expected: FAIL — `ref_to_class` raises `ModuleNotFoundError: _synthedge_target` (the module is stored
in `sys.modules` under a different key than its `__name__`).

- [ ] **Step 3: Update load_module_from_path**

Replace `load_module_from_path` in `synthedge/cli.py` with:

```python
import re  # add near the top imports if not present


def load_module_from_path(path: str) -> types.ModuleType:
    """Load a Python file as a module under a stable name == its __name__, so classes
    defined inside it round-trip through edge_case_engine.classref."""
    abspath = os.path.abspath(path)
    mod_name = "_synthedge_target_" + re.sub(r"\W", "_", abspath)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load module from: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_user_type_handlers.py tests/test_cli.py -v`
Expected: PASS (new round-trip test + all existing CLI tests still green).

- [ ] **Step 5: Commit**

```bash
git add synthedge/cli.py tests/test_user_type_handlers.py
git commit -m "fix: load target modules under a stable importable name"
```

---

### Task 6: Architecture Gate v3

**Files:**
- Modify: `tests/test_architecture_gate.py` (append)
- Test: same file

**Interfaces:**
- Consumes: resolver, codec, recipe replay, `run_fuzzer`.
- Produces: Gate-v3 assertions (spec §7): enum/dataclass generate + codec + descriptor + recipe replay
  with no fallback, plus an end-to-end `run_fuzzer` on a dataclass/enum target.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_architecture_gate.py  (append)
from tests.user_type_fixtures import Color, Priority, Point, Box
from edge_case_engine.recipe import Recipe


def test_user_types_no_fallback_and_descriptor_roundtrip():
    r = TypeResolver()
    for ann in (Color, Priority, Point, Box):
        r.resolve_tracked(ann)
    assert r.fallback_rate() == 0.0
    for ann in (Color, Priority, Point, Box):
        h = TypeResolver.resolve(ann)
        assert TypeResolver.from_descriptor(h.descriptor()).type_sig() == h.type_sig()


def test_user_type_recipe_replays_including_nan_field():
    h = TypeResolver.resolve(Box)
    budget = GenerationBudget().to_dict()
    for seed in range(200):
        rng = random.Random(seed)
        recipe = Recipe(h.descriptor(), rng.getrandbits(64), budget, [])
        a = materialize(recipe)
        b = materialize(recipe)
        assert values_equal(a, b)
        assert isinstance(a, Box)


def test_run_fuzzer_on_dataclass_enum_target(tmp_path):
    from synthedge.cli import run_fuzzer
    target = tmp_path / "ut.py"
    target.write_text(
        "from dataclasses import dataclass\n"
        "import enum\n"
        "from edge_case_engine.contracts import fuzz_contract\n"
        "class C(enum.Enum):\n"
        "    A = 1\n"
        "    B = 2\n"
        "@dataclass\n"
        "class P:\n"
        "    x: int\n"
        "    y: int\n"
        "@fuzz_contract(allowed_exceptions=(Exception,))\n"
        "def handle(p: P, c: C):\n"
        "    return (p.x, c)\n"
    )
    summary = run_fuzzer(str(target), iterations=30, seed=1)
    assert "handle" in summary and summary["handle"]["iterations"] == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_architecture_gate.py -v`
Expected: the three new tests are collected; they should pass once Tasks 1–5 are in. If any fail,
fix the responsible module from Tasks 1–5 (do not weaken the gate).

- [ ] **Step 3: No new implementation**

This task validates the assembled system.

- [ ] **Step 4: Run the full suite**

Run: `python3.14 -m pytest -q`
Expected: PASS (all previous tests + Slice 3 tests), confirming Gate v3.

- [ ] **Step 5: Commit**

```bash
git add tests/test_architecture_gate.py
git commit -m "test: architecture-gate v3 (enum + dataclass replay, end-to-end)"
```

---

## Self-Review

**Spec coverage:**
- §2.1 classref → Task 1. ✓
- §2.2 codec enum/dataclass tags (enum before int) → Task 2. ✓
- §2.3 `values_equal` dataclass branch → Task 2. ✓
- §3.1/§3.2 Enum/DataclassHandler → Task 3. ✓
- §4 resolver detection + `from_descriptor` (with R-2 graceful fallback on `get_type_hints` failure) → Task 4. ✓
- §5 leaf mutation (no engine change) → implicit; no task needed (verified by Gate v3 end-to-end run). ✓
- §6 invariants S1 (Task 1), P4 (Tasks 2, 6), H-det (Task 3). ✓
- §7 Gate v3 → Task 6. ✓
- §8 migration/file plan → Tasks 1–6. ✓
- §9 R-2 → Task 4 try/except. Dynamic-module class refs (needed for end-to-end replay) → Task 5
  (`load_module_from_path` stable naming) — an addition beyond the spec, required for §7's end-to-end.

**Placeholder scan:** No "TBD/TODO". Codec functions shown in full (placement of the enum branch is
load-bearing, so the whole function is given rather than a fragment).

**Type consistency:** `class_to_ref(cls) -> str`, `ref_to_class(ref) -> cls`, descriptors
`{"k":"enum","cls":ref}` / `{"k":"dataclass","cls":ref,"fields":{...}}`, `EnumHandler(enum_cls)`,
`DataclassHandler(cls, fields)` are used identically across Tasks 1–6. ✓

---

## Notes for the implementer

- Run `python3.14 -m pytest` after each task (the active shell `python` is 3.8 without pytest).
- `tests/user_type_fixtures.py` is a normal module (no `test_` prefix) so pytest does not collect it;
  it must be importable as `tests.user_type_fixtures` (the `tests/` package already has `__init__.py`).
- Do not touch the mutation engine, navigator, or mutators — enum/dataclass are leaf sites by design.
