# Design Spec — synthedge Engine, Slice 4 (Pydantic support)

- **Date:** 2026-06-30
- **Status:** Approved design (pre-implementation)
- **Builds on:** Slice 3 (`2026-06-30-engine-slice3-user-types-design.md`) class-identity machinery.
- **Scope:** Fuzz functions whose parameters are Pydantic v2 `BaseModel` subclasses, as an **optional**
  capability that does not affect the stdlib-only core when Pydantic is absent.

---

## 1. Purpose & goals

Pydantic models are pervasive in modern Python backends (FastAPI, data pipelines). Slice 4 lets
synthedge fuzz a function typed `def f(u: User)` by generating adversarial `User` instances, reusing
the class-identity serialization built in Slice 3.

Delivers:
1. **`PydanticHandler`** that generates model instances via `model_construct` (validation bypassed).
2. **Codec** + `values_equal` support for `BaseModel` instances, **gated** on Pydantic availability.
3. **Resolver** detection of `BaseModel` subclasses, gated.
4. A documented **boundary-fuzzing pattern** (fuzz the raw dict into `model_validate`) shipped as an
   example/test, requiring no new engine code.

### Non-goals (Slice 4)

- Adding `pydantic` to `pyproject.toml` runtime dependencies. It stays an **optional** extra; the core
  imports it softly and degrades to "unsupported type → fallback" when absent.
- Modeling Pydantic `field_validator`s, computed fields, or constraint metadata (`Field(gt=...)`).
  Generation targets field *types*; constraints are intentionally ignored (adversarial reach).
- Descending into model instances during mutation — they are **leaf** sites, like dataclass/set/tuple.
- Pydantic v1. Target is **Pydantic v2** (`model_fields`, `model_construct`, `model_validate`).

---

## 2. Optional-dependency handling (the central constraint)

The engine core must remain stdlib-only when Pydantic is not installed. One soft import, in a single
module `edge_case_engine/_pydantic.py`:

```python
try:
    import pydantic
    BaseModel = pydantic.BaseModel
except Exception:               # not installed (or import error)
    pydantic = None
    BaseModel = None

def is_model(value) -> bool:
    return BaseModel is not None and isinstance(value, BaseModel)

def is_model_type(annotation) -> bool:
    return BaseModel is not None and isinstance(annotation, type) and issubclass(annotation, BaseModel)
```

All codec/`values_equal`/resolver branches gate on `is_model(...)` / `is_model_type(...)`. When
`BaseModel is None`, every gate is `False`, so behavior is identical to pre-Slice-4. Pydantic tests use
`pytest.importorskip("pydantic")` and skip cleanly where it is absent.

---

## 3. Generation strategy: `model_construct` (validation bypassed)

`PydanticHandler.generate` builds a dict of field values (each via the field's resolved handler) and
constructs the instance with **`model_cls.model_construct(**field_values)`**.

- Verified (Pydantic 2.13): `model_construct` **bypasses validation**, so injected adversarial values
  survive as raw attributes (`User.model_construct(name=123, age=float('nan'))` yields `u.name == 123`,
  `u.age` is `nan`). This is what gives the fuzzer reach into the function's business logic.
- Rejected alternative: normal `Model(**fields)` validates and raises `ValidationError` on exactly the
  adversarial inputs we want, so it would only ever fuzz with valid data.

Determinism: fields are generated in `model_fields` declaration order, each consuming `rng` in turn.

---

## 4. Components

### 4.1 `PydanticHandler` — `type_handlers/pydantic_handler.py`

```python
class PydanticHandler(Handler):
    def __init__(self, model_cls, fields):     # fields: ordered {name: Handler}
        self.model_cls = model_cls
        self.fields = fields
    def generate(self, rng, budget):
        child = budget.child(); budget.spend(1)
        return self.model_cls.model_construct(
            **{name: h.generate(rng, child) for name, h in self.fields.items()})
    def edge_cases(self):
        yield self.model_cls.model_construct(
            **{name: next(h.edge_cases()) for name, h in self.fields.items()})
    def type_sig(self):  return f"pydantic[{self.model_cls.__qualname__}]"
    def descriptor(self):
        return {"k": "pydantic", "cls": class_to_ref(self.model_cls),
                "fields": {n: h.descriptor() for n, h in self.fields.items()}}
```

### 4.2 Codec — `edge_case_engine/codec.py` (gated)

```json
{"$t": "pydantic", "$v": ["module:Qual", {"field": <encoded>, ...}]}
```

- encode: `if is_model(value): [class_to_ref(type(value)), {n: encode(getattr(value, n)) for n in type(value).model_fields}]`.
  Use raw attribute access (`getattr`), not `model_dump` (which would coerce/serialize).
- decode: `cls = ref_to_class(ref); cls.model_construct(**{n: decode(v) for n, v in field_map.items()})`.
- `values_equal`: a Pydantic branch comparing `getattr(a, n)` vs `getattr(b, n)` for each field in
  `model_fields`, nan-aware (a model's `__eq__` would otherwise make a `nan` field compare unequal and
  break replay integrity).

### 4.3 Resolver — `type_handlers/resolver.py` (gated)

Before the unknown fallback (after the dataclass branch):

```python
if is_model_type(annotation):
    fields = {n: cls.resolve(f.annotation, strict) for n, f in annotation.model_fields.items()}
    return PydanticHandler(annotation, fields)
```

`from_descriptor` gains a `pydantic` case (import via `ref_to_class`, rebuild field handlers).
`FieldInfo.annotation` may be a PEP-604 union (`str | None`); the existing resolver already handles
`types.UnionType`.

### 4.4 Boundary mode (Mode B) — example only, no engine code

The raw-dict-into-`model_validate` pattern is just dict fuzzing plus a user-written wrapper:

```python
@fuzz_contract(allowed_exceptions=(ValidationError,))
def check_user(data: dict) -> User:
    return User.model_validate(data)
```

Shipped as an example in the spec and exercised by a test; finds validator crashes that are *not*
`ValidationError`. No new code.

---

## 5. Mutation — no engine changes

Pydantic model instances are **leaf** mutation sites: the navigator does not descend into them, and
`ScalarMutator` replaces them whole with a pool value (type-confusion fuzzing). No navigator/path/
mutator change.

---

## 6. Invariants (additions)

- **P5 (model replay):** a recipe whose value is/contains a `BaseModel` instance replays to a
  `values_equal` instance via `model_construct`; corpus integrity holds (incl. `nan` fields).
- **O1 (optional isolation):** with Pydantic absent (`BaseModel is None`), all gates are `False` and
  the engine behaves exactly as Slice 3; no import of `pydantic` occurs in the core path.
- **H-det:** `PydanticHandler.generate` is a pure function of `(rng state, budget)`.

---

## 7. Definition of Done — Architecture Gate v4

All Pydantic tests guarded by `pytest.importorskip("pydantic")`. Fixture: a `BaseModel`
`class Account(BaseModel): name: str; balance: float; tags: list[int]; nickname: Optional[str]`.

- ✓ **Generate + codec round-trip** — `Account` instances (incl. a `nan` `balance`) encode→decode to a
  `values_equal` instance; `model_construct` lets an adversarial field (e.g. `name=None`) survive.
- ✓ **Descriptor round-trip** — `from_descriptor(handler.descriptor())` reproduces an equivalent handler.
- ✓ **Replay integrity** — recipes over `Account` replay to `values_equal` instances over many seeds.
- ✓ **No fallback** — resolver maps `Account` with `fallback_rate == 0`.
- ✓ **End-to-end (Mode A)** — `run_fuzzer` on `def use(a: Account)` completes and returns a summary.
- ✓ **Boundary (Mode B)** — `run_fuzzer` on a `model_validate(data: dict)` wrapper completes; the
  pattern is demonstrated.
- ✓ **Optional isolation** — the full existing suite (132 tests) passes unchanged; with Pydantic
  hypothetically absent, no core module imports it (verified by gating, not by uninstalling).

---

## 8. Migration & file plan

New:
- `edge_case_engine/_pydantic.py` — soft import + `is_model`/`is_model_type`/`BaseModel`.
- `type_handlers/pydantic_handler.py` — `PydanticHandler`.
- `tests/test_pydantic_support.py` — handler/codec/resolver/end-to-end/Mode-B (importorskip).

Modified:
- `edge_case_engine/codec.py` — gated pydantic `encode`/`decode` + `values_equal` branch.
- `type_handlers/resolver.py` — gated `is_model_type` detection + `from_descriptor` pydantic case.
- `tests/test_architecture_gate.py` — Gate v4 cases (importorskip).
- `README.md` / `docs/` — document Mode A vs Mode B usage (optional, low priority).

Reused unchanged: classref, budget, rng, navigator, mutators, engine, scheduler, executor, corpus,
all Slice 1–3 handlers.

---

## 9. Risks & open questions

- **R-1 Pydantic absence.** Covered by §2 gating + `importorskip`; the core never hard-imports pydantic.
- **R-2 `model_fields` annotations.** A field annotation may itself be a `BaseModel` (nested model),
  resolved recursively → `PydanticHandler`; codec/replay recurse via the field encodings. Depth bound
  by `budget.child()`/accountant as elsewhere.
- **R-3 `model_construct` and private/extra attrs.** Models with `model_config = ConfigDict(extra=...)`
  or private attributes are constructed with only declared fields; this is acceptable for Slice 4
  (declared-field fuzzing). Documented.
- **R-4 Equality.** Pydantic `__eq__` compares fields and model type; the `values_equal` pydantic
  branch must short-circuit before the generic `a == b` to stay nan-aware.
- **R-5 Dynamic-module models.** Models defined in a `synthedge targets.py` file rely on the Slice 3
  stable-module-naming fix for `ref_to_class`; already in place.

---

## 10. Summary

Slice 4 adds Pydantic v2 support as an optional capability: a soft-imported `_pydantic` shim gates
codec/equality/resolver branches, and `PydanticHandler` generates adversarial instances via
`model_construct`. The high-value "fuzz the validation boundary" use case is delivered as a documented
example over existing dict fuzzing. With Pydantic absent, the engine is byte-for-byte the Slice 3 core.
