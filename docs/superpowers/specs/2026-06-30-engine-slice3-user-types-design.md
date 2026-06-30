# Design Spec — synthedge Engine, Slice 3 (User-Defined Types: Enum + dataclass)

- **Date:** 2026-06-30
- **Status:** Approved design (pre-implementation)
- **Builds on:** Slice 1 (`2026-06-29-engine-rewrite-slice1-design.md`) and Slice 2
  (`2026-06-30-engine-slice2-deep-mutation-design.md`) frozen contracts.
- **Scope:** Fuzz functions whose parameters are `Enum` subclasses or `@dataclass` types, by building
  the shared **class-identity serialization** machinery those (and later Pydantic) need.

---

## 1. Purpose & goals

synthedge can fuzz scalars, `Optional`/`Union`, `list`/`dict`/`set`/`tuple`/`Literal`. Real backends
also pass **`Enum`s and dataclasses**. Supporting them requires one new capability: **serialize an
instance of a user-declared class so a recipe replays across runs** — by class *identity*
(`module:qualname`), not by value.

Slice 3 delivers:
1. **Class-identity serialization** — a reference helper + codec tags for enum members and dataclass
   instances.
2. **`EnumHandler`** and **`DataclassHandler`** with deterministic generation and descriptor round-trip.
3. **Resolver** detection of `Enum` subclasses and dataclasses.

### Non-goals (Slice 3)

- **Pydantic** — deferred to Slice 4 (not installed in this environment, so not test-drivable; it also
  has distinct "fuzz the raw dict into `model_validate`" semantics). The class-identity machinery built
  here is the foundation Slice 4 reuses.
- **Descending into enum/dataclass nodes** during mutation. Both are **leaf** mutation sites (mutated
  whole), exactly as `set`/`tuple` are in Slice 2. No navigator/path/mutator changes.
- Branch coverage; CLI/report changes.

---

## 2. Shared machinery: class-identity serialization

### 2.1 Class reference helper — `edge_case_engine/classref.py`

```python
def class_to_ref(cls) -> str:        # "package.module:Outer.Inner"
    return f"{cls.__module__}:{cls.__qualname__}"

def ref_to_class(ref: str):          # import module, walk dotted qualname
    module, qual = ref.split(":", 1)
    obj = importlib.import_module(module)
    for part in qual.split("."):
        obj = getattr(obj, part)
    return obj
```

### 2.2 Codec tags — `edge_case_engine/codec.py`

`encode` gains two tags; **the enum check is placed before the int/float checks** (an `IntEnum`
member is also an `int`):

```json
{"$t": "enum",      "$v": ["module:Qual", "MEMBER_NAME"]}
{"$t": "dataclass", "$v": ["module:Qual", {"field": <encoded>, ...}]}
```

- Enum encode: `isinstance(value, enum.Enum)` → `[class_to_ref(type(value)), value.name]`.
  decode: `ref_to_class(ref)[name]`.
- Dataclass encode: `dataclasses.is_dataclass(value) and not isinstance(value, type)` →
  `[class_to_ref(type(value)), {f.name: encode(getattr(value, f.name)) for f in fields(value)}]`.
  decode: `ref_to_class(ref)(**{k: decode(v) for k, v in field_map.items()})`.

### 2.3 `values_equal` extension

Add a **dataclass branch**: two dataclass instances are equal iff same type and every field is
`values_equal` (nan-aware). Rationale: a dataclass's generated `__eq__` does a tuple comparison, so a
`nan` field would make a *correctly replayed* instance compare unequal and break the corpus integrity
check (`P1`/`P2`). Enum needs no change — member `==` already works.

```python
# inside values_equal, before the generic `a == b` fallback:
if dataclasses.is_dataclass(a) and not isinstance(a, type):
    if type(a) is not type(b):
        return False
    return all(values_equal(getattr(a, f.name), getattr(b, f.name))
               for f in dataclasses.fields(a))
```

---

## 3. Handlers

### 3.1 `EnumHandler` — `type_handlers/enum_handler.py`

```python
class EnumHandler(Handler):
    def __init__(self, enum_cls):
        self.enum_cls = enum_cls
        self.members = list(enum_cls)          # excludes aliases
    def generate(self, rng, budget):  return rng.choice(self.members)
    def edge_cases(self):             yield from self.members
    def type_sig(self):               return f"Enum[{self.enum_cls.__qualname__}]"
    def descriptor(self):             return {"k": "enum", "cls": class_to_ref(self.enum_cls)}
```

### 3.2 `DataclassHandler` — `type_handlers/dataclass_handler.py`

```python
class DataclassHandler(Handler):
    def __init__(self, cls, fields):           # fields: ordered {name: Handler}
        self.cls = cls
        self.fields = fields
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

Generation is deterministic: fields are generated in declaration order, each consuming `rng` in turn.
`from_descriptor` for `dataclass` imports the class via `ref_to_class` and rebuilds each field handler
from its child descriptor.

---

## 4. Resolver

`type_handlers/resolver.py` — add, **before** the unknown-annotation fallback (after the
`set`/`tuple`/`Literal` branches):

```python
if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
    return EnumHandler(annotation)
if dataclasses.is_dataclass(annotation) and isinstance(annotation, type):
    hints = typing.get_type_hints(annotation)
    fields = {f.name: cls.resolve(hints.get(f.name, None), strict)
              for f in dataclasses.fields(annotation)}
    return DataclassHandler(annotation, fields)
```

`from_descriptor` — add `enum` and `dataclass` cases (using `ref_to_class`).

---

## 5. Mutation — no engine changes

Enum members and dataclass instances are **leaf** mutation sites:
- `PathNavigator` does not descend into them (it descends only `list`/`dict`).
- `ScalarMutator.can_mutate` returns `True` for them (`not isinstance(value, (list, dict))`), so they
  are mutated by **whole-node replacement** with a value from the scalar pool — useful type-confusion
  fuzzing (e.g., passing `None` or `"synthedge"` where an `Enum`/dataclass is expected).

No new mutator, no navigator change, no path change.

---

## 6. Invariants (additions)

- **S1 (class round-trip):** `ref_to_class(class_to_ref(C)) is C` for any importable top-level or
  nested class `C`.
- **P4 (instance replay):** a recipe whose value is/contains an enum member or dataclass instance
  replays to a `values_equal` instance; corpus integrity holds (incl. `nan` dataclass fields).
- **H-det (deterministic construction):** `DataclassHandler.generate` and `EnumHandler.generate` are
  pure functions of `(rng state, budget)` (Slice 1 H1).

---

## 7. Definition of Done — Architecture Gate v3

New fixture: a stdlib `Color(enum.Enum)`, an `IntEnum`, and dataclasses
`@dataclass class Point: x: int; y: int` and `@dataclass class Box: label: str; size: float;
tag: Optional[Color]` (nested enum + Optional + a float that may be `nan`).

- ✓ **Generate + codec round-trip** — enum members and dataclass instances encode→decode to
  `values_equal` values, including a `nan` float field.
- ✓ **Descriptor round-trip** — `from_descriptor(handler.descriptor())` reproduces an equivalent
  handler (`type_sig` equal) for `Color`, `IntEnum`, `Point`, `Box`.
- ✓ **Replay integrity** — recipes over `Point`/`Box` replay to `values_equal` instances over many
  seeds (P4), including when a `nan` field is generated.
- ✓ **No fallback** — resolver maps `Color`, `IntEnum`, `Point`, `Box` with `fallback_rate == 0`.
- ✓ **End-to-end** — `run_fuzzer` on a module with a `@fuzz_contract` function taking a dataclass and
  an enum completes and returns a summary.
- ✓ All 121 existing tests stay green.

---

## 8. Migration & file plan

New:
- `edge_case_engine/classref.py` — `class_to_ref`, `ref_to_class`.
- `type_handlers/enum_handler.py` — `EnumHandler`.
- `type_handlers/dataclass_handler.py` — `DataclassHandler`.
- `tests/test_classref.py`, `tests/test_user_type_handlers.py`, `tests/test_user_type_codec.py`.

Modified:
- `edge_case_engine/codec.py` — enum/dataclass `encode`/`decode` tags; `values_equal` dataclass branch.
- `type_handlers/resolver.py` — Enum/dataclass detection + `from_descriptor` cases.
- `tests/test_architecture_gate.py` — Gate v3 cases.

Reused unchanged: budget, rng, navigator, mutators, engine, scheduler, executor, corpus, all Slice 1/2
handlers.

---

## 9. Risks & open questions

- **R-1 Recursive required dataclass fields.** A dataclass with a *required* field of its own type
  (no `Optional`/default) has no terminal value and would recurse until the size accountant/`max_depth`
  forces termination — possibly raising. Out of scope; the normal Optional/collection-nested cases are
  bounded by `budget.child()`/`spend`. Documented limitation.
- **R-2 Annotation resolvability.** `typing.get_type_hints(dataclass)` requires the class's annotations
  to be importable in scope. Test dataclasses are module-level so this holds; forward-ref-heavy classes
  may need `get_type_hints` to succeed — on failure the resolver should fall back gracefully (treat the
  whole dataclass as the unknown fallback) rather than crash. Spec'd: wrap field resolution; on
  `Exception` from `get_type_hints`, return the existing `FloatHandler` fallback and record it.
- **R-3 Enum aliases / Flag.** `list(EnumCls)` excludes aliases; name-based decode round-trips canonical
  members. `enum.Flag` combinations are not specially handled (a combined flag is still a member with a
  name only if defined); generation samples defined members. Acceptable for Slice 3.
- **R-4 Codec ordering.** Enum members are `int`/`str` subclasses for `IntEnum`/`StrEnum`; the enum
  branch must precede the bool/int/float/str branches in `encode`. Covered by §2.2 + a targeted test.

---

## 10. Summary

Slice 3 adds the **class-identity serialization** layer (a `classref` helper plus codec tags and a
nan-aware `values_equal` dataclass branch) and two handlers (`EnumHandler`, `DataclassHandler`) wired
into the resolver. Enum/dataclass values are leaf mutation sites, so the mutation engine is untouched.
This both unlocks enum/dataclass fuzzing and builds the foundation Slice 4 (Pydantic) will reuse.
