from edge_case_engine.mutators.base import Mutator
from edge_case_engine.recipe import LineageOp
from edge_case_engine.codec import encode


class ListMutator(Mutator):
    def can_mutate(self, handler, value) -> bool:
        return isinstance(value, list)

    def mutate(self, handler, value, rng, budget, path):
        new = list(value)
        op = rng.choice(["insert", "delete", "duplicate", "reverse", "empty"])
        args = {}
        elem_handler = getattr(handler, "elem", None)
        if op == "insert":
            idx = rng.randint(0, len(new))
            elem = elem_handler.generate(rng, budget.child()) if elem_handler else rng.randint(-1, 1)
            new.insert(idx, elem)
            args = {"index": idx, "value": encode(elem)}
        elif op == "delete" and new:
            idx = rng.randrange(len(new))
            del new[idx]
            args = {"index": idx}
        elif op == "duplicate" and new:
            idx = rng.randrange(len(new))
            new.insert(idx, new[idx])
            args = {"index": idx}
        elif op == "reverse":
            new.reverse()
        elif op == "empty":
            new = []
        else:  # delete/duplicate on an empty list -> fall back to inserting None
            op = "insert"
            new.insert(0, None)
            args = {"index": 0, "value": encode(None)}
        return new, LineageOp(op=f"list.{op}", path=list(path), args=args)


class DictMutator(Mutator):
    def can_mutate(self, handler, value) -> bool:
        return isinstance(value, dict)

    def mutate(self, handler, value, rng, budget, path):
        new = dict(value)
        key_handler = getattr(handler, "key", None)
        val_handler = getattr(handler, "val", None)
        op = rng.choice(["drop_key", "add_key", "corrupt_value"])
        args = {}
        keys = list(new.keys())
        if op == "drop_key" and keys:
            k = rng.choice(keys)
            del new[k]
            args = {"key": encode(k)}
        elif op == "add_key":
            k = key_handler.generate(rng, budget.child()) if key_handler else "k"
            v = val_handler.generate(rng, budget.child()) if val_handler else 0
            new[k] = v
            args = {"key": encode(k), "value": encode(v)}
        elif op == "corrupt_value" and keys:
            k = rng.choice(keys)
            corrupt = rng.choice([None, "synthedge", float("nan")])
            new[k] = corrupt
            args = {"key": encode(k), "value": encode(corrupt)}
        else:  # drop/corrupt on an empty dict -> add a key
            op = "add_key"
            new["synthedge"] = None
            args = {"key": encode("synthedge"), "value": encode(None)}
        return new, LineageOp(op=f"dict.{op}", path=list(path), args=args)
