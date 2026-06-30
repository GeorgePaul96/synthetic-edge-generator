from type_handlers.base import Handler


class TupleHandler(Handler):
    def __init__(self, elems, variadic=False):
        self.elems = list(elems)
        self.variadic = variadic

    def generate(self, rng, budget):
        if self.variadic:
            if budget.depth_exhausted():
                return ()
            n = rng.randint(0, budget.max_list_length)
            child = budget.child()
            out = []
            for _ in range(n):
                if not budget.spend(1):
                    break
                out.append(self.elems[0].generate(rng, child))
            return tuple(out)
        child = budget.child()
        return tuple(e.generate(rng, child) for e in self.elems)

    def edge_cases(self):
        if self.variadic:
            yield ()
            for v in self.elems[0].edge_cases():
                yield (v,)
        else:
            yield tuple(next(e.edge_cases()) for e in self.elems)

    def type_sig(self):
        if self.variadic:
            return f"tuple[{self.elems[0].type_sig()}, ...]"
        return "tuple[" + ", ".join(e.type_sig() for e in self.elems) + "]"

    def descriptor(self):
        return {"k": "tuple", "elems": [e.descriptor() for e in self.elems], "variadic": self.variadic}
