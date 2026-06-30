from edge_case_engine.mutators.base import Mutator
from edge_case_engine.recipe import LineageOp
from edge_case_engine.codec import encode


class ListMutator(Mutator):
    def can_mutate(self, handler, value) -> bool:
        return isinstance(value, list)

    def mutate(self, handler, value, rng, budget, path):
        op = rng.choice(["insert", "delete", "duplicate", "reverse", "empty"])
        args = {}
        elem_handler = getattr(handler, "elem", None)
        if op == "insert":
            idx = rng.randint(0, len(value))
            elem = elem_handler.generate(rng, budget.child()) if elem_handler else rng.randint(-1, 1)
            args = {"index": idx, "value": encode(elem)}
        elif op == "delete" and value:
            args = {"index": rng.randrange(len(value))}
        elif op == "duplicate" and value:
            args = {"index": rng.randrange(len(value))}
        elif op == "reverse":
            pass
        elif op == "empty":
            pass
        else:  # delete/duplicate on an empty list -> insert None at 0
            op = "insert"
            args = {"index": 0, "value": encode(None)}
        return LineageOp(op=f"list.{op}", path=list(path), args=args)


class DictMutator(Mutator):
    def can_mutate(self, handler, value) -> bool:
        return isinstance(value, dict)

    def mutate(self, handler, value, rng, budget, path):
        key_handler = getattr(handler, "key", None)
        val_handler = getattr(handler, "val", None)
        op = rng.choice(["drop_key", "add_key", "corrupt_value"])
        args = {}
        keys = list(value.keys())
        if op == "drop_key" and keys:
            args = {"key": encode(rng.choice(keys))}
        elif op == "add_key":
            k = key_handler.generate(rng, budget.child()) if key_handler else "k"
            v = val_handler.generate(rng, budget.child()) if val_handler else 0
            args = {"key": encode(k), "value": encode(v)}
        elif op == "corrupt_value" and keys:
            corrupt = rng.choice([None, "synthedge", float("nan")])
            args = {"key": encode(rng.choice(keys)), "value": encode(corrupt)}
        else:  # drop/corrupt on an empty dict -> add a key
            op = "add_key"
            args = {"key": encode("synthedge"), "value": encode(None)}
        return LineageOp(op=f"dict.{op}", path=list(path), args=args)
