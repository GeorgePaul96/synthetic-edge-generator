from type_handlers.base import Handler


class DictHandler(Handler):
    def __init__(self, key: Handler, val: Handler):
        self.key = key
        self.val = val

    def generate(self, rng, budget):
        if budget.depth_exhausted():
            return {}
        n = rng.randint(0, budget.max_dict_keys)
        child = budget.child()
        out = {}
        for _ in range(n):
            if not budget.spend(1):
                break
            k = self.key.generate(rng, child)
            try:
                out[k] = self.val.generate(rng, child)
            except TypeError:
                # unhashable generated key — skip this entry deterministically
                continue
        return out

    def edge_cases(self):
        yield {}

    def type_sig(self):
        return f"dict[{self.key.type_sig()}, {self.val.type_sig()}]"

    def descriptor(self):
        return {"k": "dict", "key": self.key.descriptor(), "val": self.val.descriptor()}
