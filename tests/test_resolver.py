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


def test_resolves_set_tuple_literal():
    from typing import Set, Tuple, Literal
    assert TypeResolver.resolve(Set[int]).type_sig() == "set[int]"
    assert TypeResolver.resolve(Tuple[int, str]).type_sig() == "tuple[int, str]"
    assert TypeResolver.resolve(Tuple[int, ...]).type_sig() == "tuple[int, ...]"
    assert TypeResolver.resolve(Literal["a", "b"]).type_sig() == "Literal['a', 'b']"


def test_set_tuple_literal_descriptor_roundtrip():
    from typing import Set, Tuple, Literal
    for ann in [Set[int], Tuple[int, str], Tuple[int, ...], Literal[1, 2, 3]]:
        h = TypeResolver.resolve(ann)
        assert TypeResolver.from_descriptor(h.descriptor()).type_sig() == h.type_sig()
