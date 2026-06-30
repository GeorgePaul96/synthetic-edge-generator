# Engine Slice 4 (Pydantic support) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fuzz functions whose parameters are Pydantic v2 `BaseModel` subclasses, as an optional capability that leaves the stdlib-only core unchanged when Pydantic is absent.

**Architecture:** A soft-import shim (`edge_case_engine/_pydantic.py`) gates codec/equality/resolver branches on Pydantic availability. `PydanticHandler` generates adversarial instances via `model_construct` (validation bypassed); the codec serializes models by class-identity + raw field values.

**Tech Stack:** Python 3.9+ (stdlib core), Pydantic v2 (optional, installed for tests: 2.13.4), pytest.

## Global Constraints

- Python **3.9+**; **stdlib only** for the core. Pydantic is an **optional** dependency — **not** added
  to `pyproject.toml` runtime deps.
- With Pydantic absent (`BaseModel is None`), every gate is `False` and behavior equals Slice 3
  (invariant O1). No core module hard-imports `pydantic`.
- Generation uses **`model_construct`** (bypasses validation); codec reads fields via **`getattr`**
  (not `model_dump`).
- Pydantic model instances are **leaf** mutation sites — no navigator/path/mutator changes.
- All Pydantic tests guard with `pytest.importorskip("pydantic")`.
- Test interpreter: `python3.14 -m pytest`. All 132 existing tests stay green.
- Reference spec: `docs/superpowers/specs/2026-06-30-engine-slice4-pydantic-design.md`.
- Commit after every task.

---

## File Structure

New files:
- `edge_case_engine/_pydantic.py` — soft import + `BaseModel`, `is_model`, `is_model_type`
- `type_handlers/pydantic_handler.py` — `PydanticHandler`
- `tests/pydantic_fixtures.py` — `Account` model (imported only after `importorskip`)
- `tests/test_pydantic_support.py` — shim/codec/handler/resolver/gate/Mode-A/Mode-B (module-level skip)

Modified files:
- `edge_case_engine/codec.py` — gated pydantic `encode`/`decode` + `values_equal` branch
- `type_handlers/resolver.py` — gated detection + `from_descriptor` pydantic case

> Note on test placement: the Gate-v4 Pydantic cases live in `tests/test_pydantic_support.py` (which
> uses a module-level `importorskip`), not in `tests/test_architecture_gate.py` (which must stay
> collectable without Pydantic). This is a deliberate refinement of spec §8.

---

### Task 1: Pydantic soft-import shim + fixtures

**Files:**
- Create: `edge_case_engine/_pydantic.py`, `tests/pydantic_fixtures.py`, `tests/test_pydantic_support.py`
- Test: `tests/test_pydantic_support.py`

**Interfaces:**
- Consumes: `pydantic` (optional).
- Produces: `BaseModel` (the class or `None`), `is_model(value) -> bool`,
  `is_model_type(annotation) -> bool`. Fixture `Account(BaseModel)` with fields
  `name: str; balance: float; tags: List[int]; nickname: Optional[str]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/pydantic_fixtures.py
from typing import Optional, List
from pydantic import BaseModel


class Account(BaseModel):
    name: str
    balance: float
    tags: List[int]
    nickname: Optional[str]
```

```python
# tests/test_pydantic_support.py
import pytest

pydantic = pytest.importorskip("pydantic")   # whole module skips if Pydantic is absent

from edge_case_engine._pydantic import is_model, is_model_type, BaseModel
from tests.pydantic_fixtures import Account


def test_shim_detects_models():
    assert BaseModel is not None
    assert is_model_type(Account) is True
    inst = Account.model_construct(name="a", balance=1.0, tags=[], nickname=None)
    assert is_model(inst) is True
    assert is_model_type(int) is False
    assert is_model(5) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_pydantic_support.py -v`
Expected: FAIL with `ModuleNotFoundError: edge_case_engine._pydantic`.

- [ ] **Step 3: Write minimal implementation**

```python
# edge_case_engine/_pydantic.py
try:
    import pydantic
    BaseModel = pydantic.BaseModel
except Exception:                 # Pydantic not installed (or import error)
    pydantic = None
    BaseModel = None


def is_model(value) -> bool:
    return BaseModel is not None and isinstance(value, BaseModel)


def is_model_type(annotation) -> bool:
    return (BaseModel is not None
            and isinstance(annotation, type)
            and issubclass(annotation, BaseModel))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_pydantic_support.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/_pydantic.py tests/pydantic_fixtures.py tests/test_pydantic_support.py
git commit -m "feat: add Pydantic soft-import shim + fixtures"
```

---

### Task 2: Codec pydantic tags + values_equal branch (gated)

**Files:**
- Modify: `edge_case_engine/codec.py`
- Test: `tests/test_pydantic_support.py` (append)

**Interfaces:**
- Consumes: `_pydantic.is_model`, `classref.class_to_ref`/`ref_to_class`.
- Produces: `encode`/`decode` round-trip `BaseModel` instances (`{"$t":"pydantic",...}`) via
  `model_construct`; `values_equal` compares model instances field-wise (nan-aware).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydantic_support.py  (append)
import math
from edge_case_engine.codec import encode, decode, values_equal


def test_model_codec_roundtrip_including_nan_and_adversarial_field():
    # model_construct bypasses validation: name=None (declared str) survives
    acct = Account.model_construct(name=None, balance=float("nan"), tags=[1, 2], nickname="n")
    restored = decode(encode(acct))
    assert values_equal(restored, acct)
    assert restored.name is None
    assert math.isnan(restored.balance)


def test_values_equal_model_distinguishes_fields():
    a = Account.model_construct(name="a", balance=1.0, tags=[], nickname=None)
    b = Account.model_construct(name="a", balance=1.0, tags=[], nickname=None)
    c = Account.model_construct(name="a", balance=2.0, tags=[], nickname=None)
    assert values_equal(a, b) is True
    assert values_equal(a, c) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_pydantic_support.py::test_model_codec_roundtrip_including_nan_and_adversarial_field -v`
Expected: FAIL — `encode(acct)` raises `TypeError: codec cannot encode <class '...Account'>`.

- [ ] **Step 3: Update the codec**

Add an import near the top of `edge_case_engine/codec.py` (after the existing `classref` import):

```python
from edge_case_engine._pydantic import is_model
```

In `encode`, add a branch immediately before the final `raise TypeError(...)`:

```python
    if is_model(value):
        return {"$t": "pydantic", "$v": [
            class_to_ref(type(value)),
            {n: encode(getattr(value, n)) for n in type(value).model_fields},
        ]}
    raise TypeError(f"codec cannot encode {type(value)!r}")
```

In `decode`, add a branch alongside the other tags (before the final `raise ValueError`):

```python
        if t == "pydantic":
            ref, field_map = obj["$v"]
            cls = ref_to_class(ref)
            return cls.model_construct(**{k: decode(v) for k, v in field_map.items()})
```

In `values_equal`, add a branch immediately before the final `return a == b` (after the dataclass
branch):

```python
    if is_model(a):
        return all(values_equal(getattr(a, n), getattr(b, n)) for n in type(a).model_fields)
    return a == b
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_pydantic_support.py tests/test_codec.py -v`
Expected: PASS (pydantic codec tests + existing codec tests).

- [ ] **Step 5: Commit**

```bash
git add edge_case_engine/codec.py tests/test_pydantic_support.py
git commit -m "feat: codec pydantic model tags with nan-aware equality (gated)"
```

---

### Task 3: PydanticHandler

**Files:**
- Create: `type_handlers/pydantic_handler.py`
- Test: `tests/test_pydantic_support.py` (append)

**Interfaces:**
- Consumes: `Handler`, `GenerationBudget`, `classref.class_to_ref`.
- Produces: `PydanticHandler(model_cls, fields)` — `.model_cls`, `.fields` (ordered `{name: Handler}`);
  `generate` returns `model_cls.model_construct(**{name: h.generate(...)})`; `type_sig
  "pydantic[<Qual>]"`; `descriptor {"k":"pydantic","cls":ref,"fields":{name: child_desc}}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydantic_support.py  (append)
import random
from edge_case_engine.budget import GenerationBudget
from type_handlers.pydantic_handler import PydanticHandler
from type_handlers.scalars import IntegerHandler, FloatHandler


def test_pydantic_handler_constructs_instance_deterministically():
    # Account requires name/balance/tags/nickname; build matching field handlers
    from type_handlers.list_handler import ListHandler
    from type_handlers.scalars import StringHandler
    from type_handlers.optional_handler import OptionalHandler
    fields = {"name": StringHandler(), "balance": FloatHandler(),
              "tags": ListHandler(IntegerHandler()), "nickname": OptionalHandler(StringHandler())}
    h = PydanticHandler(Account, fields)
    v1 = h.generate(random.Random(2), GenerationBudget())
    v2 = h.generate(random.Random(2), GenerationBudget())
    assert is_model(v1) and values_equal(v1, v2)
    assert h.type_sig() == "pydantic[Account]"
    assert h.descriptor()["k"] == "pydantic" and "balance" in h.descriptor()["fields"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_pydantic_support.py::test_pydantic_handler_constructs_instance_deterministically -v`
Expected: FAIL with `ModuleNotFoundError: type_handlers.pydantic_handler`.

- [ ] **Step 3: Write minimal implementation**

```python
# type_handlers/pydantic_handler.py
from type_handlers.base import Handler
from edge_case_engine.classref import class_to_ref


class PydanticHandler(Handler):
    def __init__(self, model_cls, fields):
        self.model_cls = model_cls
        self.fields = fields            # ordered dict {name: Handler}

    def generate(self, rng, budget):
        child = budget.child()
        budget.spend(1)
        values = {name: h.generate(rng, child) for name, h in self.fields.items()}
        return self.model_cls.model_construct(**values)   # bypasses validation (adversarial)

    def edge_cases(self):
        yield self.model_cls.model_construct(
            **{name: next(h.edge_cases()) for name, h in self.fields.items()})

    def type_sig(self):
        return f"pydantic[{self.model_cls.__qualname__}]"

    def descriptor(self):
        return {"k": "pydantic", "cls": class_to_ref(self.model_cls),
                "fields": {n: h.descriptor() for n, h in self.fields.items()}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_pydantic_support.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add type_handlers/pydantic_handler.py tests/test_pydantic_support.py
git commit -m "feat: add PydanticHandler (model_construct generation)"
```

---

### Task 4: Resolver detection + from_descriptor (gated)

**Files:**
- Modify: `type_handlers/resolver.py`
- Test: `tests/test_pydantic_support.py` (append)

**Interfaces:**
- Consumes: `_pydantic.is_model_type`, `PydanticHandler`, `classref.ref_to_class`.
- Produces: `TypeResolver.resolve` maps `BaseModel` subclasses → `PydanticHandler` (resolving each
  field via `model_fields[*].annotation`); `from_descriptor` handles `pydantic`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydantic_support.py  (append)
from type_handlers.resolver import TypeResolver
from type_handlers.pydantic_handler import PydanticHandler as _PH


def test_resolver_maps_model_and_roundtrips_descriptor():
    h = TypeResolver.resolve(Account)
    assert isinstance(h, _PH)
    assert set(h.fields.keys()) == {"name", "balance", "tags", "nickname"}
    assert TypeResolver.from_descriptor(h.descriptor()).type_sig() == h.type_sig()
    r = TypeResolver()
    r.resolve_tracked(Account)
    assert r.fallback_rate() == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3.14 -m pytest tests/test_pydantic_support.py::test_resolver_maps_model_and_roundtrips_descriptor -v`
Expected: FAIL (`Account` resolves to the `FloatHandler` fallback, so `isinstance(h, PydanticHandler)`
is False).

- [ ] **Step 3: Update the resolver**

Add imports at the top of `type_handlers/resolver.py`:

```python
from type_handlers.pydantic_handler import PydanticHandler
from edge_case_engine._pydantic import is_model_type
```

In `resolve`, add a branch **before** the unknown-annotation fallback (after the dataclass branch):

```python
        if is_model_type(annotation):
            fields = {n: cls.resolve(f.annotation, strict)
                      for n, f in annotation.model_fields.items()}
            return PydanticHandler(annotation, fields)
```

In `from_descriptor`, add a case (before the final `raise`):

```python
        if k == "pydantic":
            cls_obj = ref_to_class(desc["cls"])
            fields = {n: cls.from_descriptor(d) for n, d in desc["fields"].items()}
            return PydanticHandler(cls_obj, fields)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3.14 -m pytest tests/test_pydantic_support.py tests/test_resolver.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add type_handlers/resolver.py tests/test_pydantic_support.py
git commit -m "feat: resolve Pydantic BaseModel annotations to handlers (gated)"
```

---

### Task 5: Architecture Gate v4 + Mode A/B end-to-end

**Files:**
- Modify: `tests/test_pydantic_support.py` (append)
- Test: same file

**Interfaces:**
- Consumes: resolver, recipe replay, `run_fuzzer`.
- Produces: Gate-v4 assertions (spec §7): replay integrity over `Account` incl. nan; end-to-end Mode A
  (model param) and Mode B (`model_validate` over a dict param).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pydantic_support.py  (append)
from edge_case_engine.recipe import Recipe, materialize


def test_account_recipe_replays_over_many_seeds():
    h = TypeResolver.resolve(Account)
    budget = GenerationBudget().to_dict()
    for seed in range(100):
        rng = random.Random(seed)
        recipe = Recipe(h.descriptor(), rng.getrandbits(64), budget, [])
        a = materialize(recipe)
        b = materialize(recipe)
        assert values_equal(a, b)
        assert values_equal(decode(encode(a)), a)


def test_run_fuzzer_mode_a_model_param(tmp_path):
    from synthedge.cli import run_fuzzer
    target = tmp_path / "ma.py"
    target.write_text(
        "from pydantic import BaseModel\n"
        "from edge_case_engine.contracts import fuzz_contract\n"
        "class A(BaseModel):\n"
        "    x: int\n"
        "    y: float\n"
        "@fuzz_contract(allowed_exceptions=(Exception,))\n"
        "def use(a: A):\n"
        "    return a.x\n"
    )
    summary = run_fuzzer(str(target), iterations=30, seed=1)
    assert "use" in summary and summary["use"]["iterations"] == 30


def test_run_fuzzer_mode_b_model_validate(tmp_path):
    from synthedge.cli import run_fuzzer
    target = tmp_path / "mb.py"
    target.write_text(
        "from pydantic import BaseModel, ValidationError\n"
        "from edge_case_engine.contracts import fuzz_contract\n"
        "class A(BaseModel):\n"
        "    x: int\n"
        "@fuzz_contract(allowed_exceptions=(ValidationError, TypeError))\n"
        "def check(data: dict) -> A:\n"
        "    return A.model_validate(data)\n"
    )
    summary = run_fuzzer(str(target), iterations=30, seed=1)
    assert "check" in summary and summary["check"]["iterations"] == 30
```

- [ ] **Step 2: Run test to verify it fails (or passes if Tasks 1–4 complete)**

Run: `python3.14 -m pytest tests/test_pydantic_support.py -v`
Expected: PASS once Tasks 1–4 are in. If a sub-assertion fails, fix the responsible module from
Tasks 1–4 (do not weaken the gate).

- [ ] **Step 3: No new implementation**

This task validates the assembled system end-to-end (Mode A: model parameter; Mode B: `model_validate`
boundary fuzzing over a `dict` param — no engine code, just a user wrapper).

- [ ] **Step 4: Run the full suite**

Run: `python3.14 -m pytest -q`
Expected: PASS (all 132 prior tests + the Pydantic suite), confirming Gate v4 and optional isolation.

- [ ] **Step 5: Commit**

```bash
git add tests/test_pydantic_support.py
git commit -m "test: architecture-gate v4 (pydantic replay + Mode A/B end-to-end)"
```

---

## Self-Review

**Spec coverage:**
- §2 soft-import shim + gating → Task 1 (`_pydantic`); gates applied in Tasks 2, 4. ✓
- §3 `model_construct` generation → Task 3. ✓
- §4.1 `PydanticHandler` → Task 3. ✓
- §4.2 codec encode/decode + `values_equal` (getattr, not model_dump) → Task 2. ✓
- §4.3 resolver detection + `from_descriptor` → Task 4. ✓
- §4.4 Mode B example → Task 5 (`test_run_fuzzer_mode_b_model_validate`). ✓
- §5 leaf mutation (no engine change) → implicit; verified by Task 5 Mode A end-to-end. ✓
- §6 invariants P5 (Tasks 2, 5), O1 (Task 1 gating + `importorskip`), H-det (Task 3). ✓
- §7 Gate v4 → Task 5 (placed in `test_pydantic_support.py`, per the file-structure note). ✓
- §8 migration/file plan → Tasks 1–5. ✓

**Placeholder scan:** No "TBD/TODO". Codec changes given as exact insertions with surrounding anchors.

**Type consistency:** `is_model(value)`, `is_model_type(annotation)`, `BaseModel`,
`PydanticHandler(model_cls, fields)`, descriptor `{"k":"pydantic","cls":ref,"fields":{...}}`, codec tag
`{"$t":"pydantic","$v":[ref, field_map]}` are used identically across Tasks 1–5. ✓

---

## Notes for the implementer

- Run `python3.14 -m pytest` after each task (Pydantic 2.13.4 is installed in that interpreter).
- Every Pydantic test relies on the module-level `pytest.importorskip("pydantic")` in
  `tests/test_pydantic_support.py`; do not import `pydantic` or `tests.pydantic_fixtures` above it.
- Do not add `pydantic` to `pyproject.toml` — it stays an optional extra.
- Do not touch the mutation engine — Pydantic models are leaf sites by design.
