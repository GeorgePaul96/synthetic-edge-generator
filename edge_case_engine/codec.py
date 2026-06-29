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
        sa = sorted(a, key=repr)
        sb = sorted(b, key=repr)
        return len(sa) == len(sb) and all(values_equal(x, y) for x, y in zip(sa, sb))
    if isinstance(a, dict):
        ka = sorted(a.keys(), key=repr)
        kb = sorted(b.keys(), key=repr)
        if len(ka) != len(kb) or not all(values_equal(x, y) for x, y in zip(ka, kb)):
            return False
        return all(values_equal(a[x], b[y]) for x, y in zip(ka, kb))
    return a == b
