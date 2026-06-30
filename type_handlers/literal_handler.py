from type_handlers.base import Handler
from edge_case_engine.codec import encode


class LiteralHandler(Handler):
    def __init__(self, values):
        self.values = list(values)

    def generate(self, rng, budget):
        return rng.choice(self.values)

    def edge_cases(self):
        for v in self.values:
            yield v

    def type_sig(self):
        return "Literal[" + ", ".join(repr(v) for v in self.values) + "]"

    def descriptor(self):
        return {"k": "literal", "values": [encode(v) for v in self.values]}
