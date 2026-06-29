from type_handlers.base import Handler


class UnionHandler(Handler):
    def __init__(self, options):
        self.options = list(options)

    def generate(self, rng, budget):
        weights = list(budget.union_weights) if budget.union_weights else None
        if weights and len(weights) == len(self.options):
            chosen = rng.choices(self.options, weights=weights, k=1)[0]
        else:
            chosen = rng.choice(self.options)
        return chosen.generate(rng, budget)

    def edge_cases(self):
        iters = [o.edge_cases() for o in self.options]
        exhausted = 0
        while exhausted < len(iters):
            exhausted = 0
            for it in iters:
                try:
                    yield next(it)
                except StopIteration:
                    exhausted += 1

    def type_sig(self):
        return "Union[" + ", ".join(o.type_sig() for o in self.options) + "]"

    def descriptor(self):
        return {"k": "union", "options": [o.descriptor() for o in self.options]}
