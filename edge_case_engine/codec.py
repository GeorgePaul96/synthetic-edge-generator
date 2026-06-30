import base64
import math
import enum
import dataclasses

from edge_case_engine.classref import class_to_ref, ref_to_class
from edge_case_engine._pydantic import is_model


def encode(value):
    if isinstance(value, enum.Enum):       # before int/float/str (IntEnum/StrEnum members)
        return {"$t": "enum", "$v": [class_to_ref(type(value)), value.name]}
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
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {"$t": "dataclass", "$v": [
            class_to_ref(type(value)),
            {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)},
        ]}
    if is_model(value):
        return {"$t": "pydantic", "$v": [
            class_to_ref(type(value)),
            {n: encode(getattr(value, n)) for n in type(value).model_fields},
        ]}
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
        if t == "enum":
            ref, name = obj["$v"]
            return ref_to_class(ref)[name]
        if t == "dataclass":
            ref, field_map = obj["$v"]
            cls = ref_to_class(ref)
            return cls(**{k: decode(v) for k, v in field_map.items()})
        if t == "pydantic":
            ref, field_map = obj["$v"]
            cls = ref_to_class(ref)
            return cls.model_construct(**{k: decode(v) for k, v in field_map.items()})
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
        sa = sorted(a, key=repr)
        sb = sorted(b, key=repr)
        return len(sa) == len(sb) and all(values_equal(x, y) for x, y in zip(sa, sb))
    if isinstance(a, dict):
        ka = sorted(a.keys(), key=repr)
        kb = sorted(b.keys(), key=repr)
        if len(ka) != len(kb) or not all(values_equal(x, y) for x, y in zip(ka, kb)):
            return False
        return all(values_equal(a[x], b[y]) for x, y in zip(ka, kb))
    if dataclasses.is_dataclass(a) and not isinstance(a, type):
        return all(values_equal(getattr(a, f.name), getattr(b, f.name))
                   for f in dataclasses.fields(a))
    if is_model(a):
        return all(values_equal(getattr(a, n), getattr(b, n)) for n in type(a).model_fields)
    return a == b
