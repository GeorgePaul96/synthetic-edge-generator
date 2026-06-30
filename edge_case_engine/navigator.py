from edge_case_engine.codec import encode
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


def _matches(handler, value):
    if isinstance(handler, BoolHandler):
        return isinstance(value, bool)
    if isinstance(handler, IntegerHandler):
        return isinstance(value, int) and not isinstance(value, bool)
    if isinstance(handler, FloatHandler):
        return isinstance(value, float)
    if isinstance(handler, StringHandler):
        return isinstance(value, str)
    if isinstance(handler, NoneHandler):
        return value is None
    if isinstance(handler, ListHandler):
        return isinstance(value, list)
    if isinstance(handler, DictHandler):
        return isinstance(value, dict)
    if isinstance(handler, SetHandler):
        return isinstance(value, set)
    if isinstance(handler, TupleHandler):
        return isinstance(value, tuple)
    if isinstance(handler, LiteralHandler):
        return value in handler.values
    if isinstance(handler, OptionalHandler):
        return value is None or _matches(handler.inner, value)
    if isinstance(handler, UnionHandler):
        return any(_matches(o, value) for o in handler.options)
    return False


def effective_handler(handler, value):
    """Unwrap Optional/Union to the handler matching the concrete runtime value."""
    if isinstance(handler, OptionalHandler):
        return effective_handler(handler.inner, value) if value is not None else handler
    if isinstance(handler, UnionHandler):
        for opt in handler.options:
            if _matches(opt, value):
                return effective_handler(opt, value)
        return handler
    return handler


class PathNavigator:
    def __init__(self, stop_prob: float = 0.5):
        self.stop_prob = stop_prob

    def _descend_options(self, handler, value):
        opts = []
        if isinstance(handler, ListHandler) and isinstance(value, list) and value:
            for i in range(len(value)):
                opts.append((["list", i], handler.elem, value[i]))
        elif isinstance(handler, DictHandler) and isinstance(value, dict) and value:
            for k in value.keys():
                opts.append((["dict", encode(k)], handler.val, value[k]))
        return opts

    def select(self, handler, value, rng):
        path = []
        h, v = effective_handler(handler, value), value
        while True:
            options = self._descend_options(h, v)
            if not options or rng.random() < self.stop_prob:
                return path, h, v
            seg, child_h, child_v = rng.choice(options)
            path.append(seg)
            h, v = effective_handler(child_h, child_v), child_v
