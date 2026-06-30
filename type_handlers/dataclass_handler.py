from type_handlers.base import Handler
from edge_case_engine.classref import class_to_ref


class DataclassHandler(Handler):
    def __init__(self, cls, fields):
        self.cls = cls
        self.fields = fields            # ordered dict {name: Handler}

    def generate(self, rng, budget):
        child = budget.child()
        budget.spend(1)
        kwargs = {name: h.generate(rng, child) for name, h in self.fields.items()}
        return self.cls(**kwargs)

    def edge_cases(self):
        yield self.cls(**{name: next(h.edge_cases()) for name, h in self.fields.items()})

    def type_sig(self):
        return f"dataclass[{self.cls.__qualname__}]"

    def descriptor(self):
        return {"k": "dataclass", "cls": class_to_ref(self.cls),
                "fields": {n: h.descriptor() for n, h in self.fields.items()}}
