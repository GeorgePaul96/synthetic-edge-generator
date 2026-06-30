from type_handlers.base import Handler
from edge_case_engine.classref import class_to_ref


class PydanticHandler(Handler):
    def __init__(self, model_cls, fields):
        self.model_cls = model_cls
        self.fields = fields            # ordered dict {name: Handler}

    def generate(self, rng, budget):
        child = budget.child()
        budget.spend(1)
        values = {name: h.generate(rng, child) for name, h in self.fields.items()}
        return self.model_cls.model_construct(**values)   # bypasses validation (adversarial)

    def edge_cases(self):
        yield self.model_cls.model_construct(
            **{name: next(h.edge_cases()) for name, h in self.fields.items()})

    def type_sig(self):
        return f"pydantic[{self.model_cls.__qualname__}]"

    def descriptor(self):
        return {"k": "pydantic", "cls": class_to_ref(self.model_cls),
                "fields": {n: h.descriptor() for n, h in self.fields.items()}}
