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
