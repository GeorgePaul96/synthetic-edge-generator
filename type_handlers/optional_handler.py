from type_handlers.base import Handler


class OptionalHandler(Handler):
    def __init__(self, inner: Handler):
        self.inner = inner

    def generate(self, rng, budget):
        if rng.random() < budget.probability_none:
            return None
        return self.inner.generate(rng, budget)

    def edge_cases(self):
        yield None
        for v in self.inner.edge_cases():
            yield v

    def type_sig(self):
        return f"Optional[{self.inner.type_sig()}]"

    def descriptor(self):
        return {"k": "optional", "inner": self.inner.descriptor()}
