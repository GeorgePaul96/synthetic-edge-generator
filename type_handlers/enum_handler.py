from type_handlers.base import Handler
from edge_case_engine.classref import class_to_ref


class EnumHandler(Handler):
    def __init__(self, enum_cls):
        self.enum_cls = enum_cls
        self.members = list(enum_cls)

    def generate(self, rng, budget):
        return rng.choice(self.members)

    def edge_cases(self):
        for m in self.members:
            yield m

    def type_sig(self):
        return f"Enum[{self.enum_cls.__qualname__}]"

    def descriptor(self):
        return {"k": "enum", "cls": class_to_ref(self.enum_cls)}
