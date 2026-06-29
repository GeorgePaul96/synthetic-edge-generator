from type_handlers.base import Handler


class ListHandler(Handler):
    def __init__(self, elem: Handler):
        self.elem = elem

    def generate(self, rng, budget):
        if budget.depth_exhausted():
            return []
        length = rng.randint(0, budget.max_list_length)
        child = budget.child()
        out = []
        for _ in range(length):
            if not budget.spend(1):
                break
            out.append(self.elem.generate(rng, child))
        return out

    def edge_cases(self):
        yield []
        for v in self.elem.edge_cases():
            yield [v]

    def type_sig(self):
        return f"list[{self.elem.type_sig()}]"

    def descriptor(self):
        return {"k": "list", "elem": self.elem.descriptor()}
