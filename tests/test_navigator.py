import random
from typing import List, Dict, Optional

from type_handlers.resolver import TypeResolver
from type_handlers.scalars import IntegerHandler
from type_handlers.optional_handler import OptionalHandler
from edge_case_engine.navigator import PathNavigator, effective_handler
from edge_case_engine.recipe import _get_node


def test_effective_handler_unwraps_optional():
    h = TypeResolver.resolve(Optional[int])
    assert isinstance(effective_handler(h, 5), IntegerHandler)
    assert isinstance(effective_handler(h, None), OptionalHandler)


def test_navigator_path_is_sound():
    h = TypeResolver.resolve(List[Dict[str, int]])
    value = [{"a": 1, "b": 2}, {"c": 3}]
    nav = PathNavigator(stop_prob=0.0)   # descend all the way to a leaf
    for s in range(50):
        path, sub_h, sub_v = nav.select(h, value, random.Random(s))
        assert _get_node(value, path) == sub_v


def test_navigator_leaf_on_scalar():
    h = IntegerHandler()
    path, sub_h, sub_v = PathNavigator().select(h, 7, random.Random(0))
    assert path == [] and sub_v == 7
