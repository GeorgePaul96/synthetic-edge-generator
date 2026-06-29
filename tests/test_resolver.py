from typing import Optional, Union, List, Dict

from type_handlers.resolver import TypeResolver
from type_handlers.scalars import FloatHandler, NoneHandler


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


def test_unannotated_is_fallback_but_nonetype_is_none_handler():
    assert isinstance(TypeResolver.resolve(None), FloatHandler)      # unannotated
    assert isinstance(TypeResolver.resolve(type(None)), NoneHandler)  # explicit NoneType
