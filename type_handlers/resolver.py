import types
import typing
import enum
import dataclasses

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
from type_handlers.enum_handler import EnumHandler
from type_handlers.dataclass_handler import DataclassHandler
from edge_case_engine.codec import decode as _decode
from edge_case_engine.classref import ref_to_class

_NONE = type(None)
_SCALARS = {float: FloatHandler, int: IntegerHandler, str: StringHandler, bool: BoolHandler}
_UNION_TYPE = getattr(types, "UnionType", None)  # PEP 604 `X | Y` (3.10+)


class _FallbackCounter:
    count = 0


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
        if annotation is _NONE:
            return NoneHandler()                 # explicit NoneType annotation
        if annotation is None:
            # unannotated parameter -> fallback
            if strict:
                raise TypeError("unannotated parameter")
            _FallbackCounter.count += 1
            return FloatHandler()
        if annotation in _SCALARS:
            return _SCALARS[annotation]()

        origin = typing.get_origin(annotation)
        args = typing.get_args(annotation)

        if origin is list:
            return ListHandler(cls.resolve(args[0], strict) if args else FloatHandler())
        if origin is dict:
            if len(args) == 2:
                return DictHandler(cls.resolve(args[0], strict), cls.resolve(args[1], strict))
            return DictHandler(StringHandler(), FloatHandler())
        if origin is typing.Union or (_UNION_TYPE is not None and origin is _UNION_TYPE):
            non_none = [a for a in args if a is not _NONE]
            has_none = len(non_none) != len(args)
            inner = (cls.resolve(non_none[0], strict) if len(non_none) == 1
                     else UnionHandler([cls.resolve(a, strict) for a in non_none]))
            return OptionalHandler(inner) if has_none else inner
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

        # unknown annotation
        if strict:
            raise TypeError(f"no handler for annotation {annotation!r}")
        _FallbackCounter.count += 1
        return FloatHandler()

    @classmethod
    def from_descriptor(cls, desc):
        k = desc["k"]
        if k == "float":
            return FloatHandler()
        if k == "int":
            return IntegerHandler()
        if k == "str":
            return StringHandler()
        if k == "bool":
            return BoolHandler()
        if k == "none":
            return NoneHandler()
        if k == "list":
            return ListHandler(cls.from_descriptor(desc["elem"]))
        if k == "dict":
            return DictHandler(cls.from_descriptor(desc["key"]), cls.from_descriptor(desc["val"]))
        if k == "optional":
            return OptionalHandler(cls.from_descriptor(desc["inner"]))
        if k == "union":
            return UnionHandler([cls.from_descriptor(o) for o in desc["options"]])
        if k == "set":
            return SetHandler(cls.from_descriptor(desc["elem"]))
        if k == "tuple":
            return TupleHandler([cls.from_descriptor(e) for e in desc["elems"]],
                                variadic=desc["variadic"])
        if k == "literal":
            return LiteralHandler([_decode(v) for v in desc["values"]])
        if k == "enum":
            return EnumHandler(ref_to_class(desc["cls"]))
        if k == "dataclass":
            cls_obj = ref_to_class(desc["cls"])
            fields = {n: cls.from_descriptor(d) for n, d in desc["fields"].items()}
            return DataclassHandler(cls_obj, fields)
        raise ValueError(f"unknown descriptor kind {k!r}")
