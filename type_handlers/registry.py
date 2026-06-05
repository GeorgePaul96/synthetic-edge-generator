from type_handlers.float_handler import FloatHandler
from type_handlers.integer_handler import IntegerHandler
from type_handlers.string_handler import StringHandler
from type_handlers.bool_handler import BoolHandler


class HandlerRegistry:
    _TYPE_MAP = {
        float: FloatHandler,
        int: IntegerHandler,
        str: StringHandler,
        bool: BoolHandler,
    }

    @classmethod
    def handlers_for_params(cls, parameters: tuple, annotations: dict) -> list:
        """
        Build a handler list matching the function's parameter types.
        parameters: tuple of parameter names from FuzzTarget
        annotations: dict of param_name -> type from typing.get_type_hints or __annotations__
        Falls back to FloatHandler per unknown/unannotated param.
        """
        handlers = []
        for param in parameters:
            annotation = annotations.get(param, None)
            handler_class = cls._TYPE_MAP.get(annotation, None)
            if handler_class is not None:
                handlers.append(handler_class())
            else:
                # Unknown type or no annotation: use float fallback
                handlers.append(FloatHandler())
        return handlers
