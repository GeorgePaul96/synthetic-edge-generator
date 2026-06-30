from type_handlers.base import Handler


class SetHandler(Handler):
    def __init__(self, elem):
        self.elem = elem

    def generate(self, rng, budget):
        if budget.depth_exhausted():
            return set()
        n = rng.randint(0, budget.max_list_length)
        child = budget.child()
        out = set()
        for _ in range(n):
            if not budget.spend(1):
                break
            v = self.elem.generate(rng, child)
            try:
                out.add(v)
            except TypeError:
                continue  # unhashable generated element
        return out

    def edge_cases(self):
        yield set()
        for v in self.elem.edge_cases():
            try:
                s = {v}
            except TypeError:
                continue
            yield s

    def type_sig(self):
        return f"set[{self.elem.type_sig()}]"

    def descriptor(self):
        return {"k": "set", "elem": self.elem.descriptor()}
