import random
from dataclasses import dataclass, field, asdict

from edge_case_engine.budget import GenerationBudget
from edge_case_engine.codec import decode
from type_handlers.resolver import TypeResolver


@dataclass
class LineageOp:
    op: str
    path: list = field(default_factory=list)
    args: dict = field(default_factory=dict)


@dataclass
class Recipe:
    descriptor: dict
    seed: int
    budget: dict
    lineage: list = field(default_factory=list)

    def type_sig(self) -> str:
        return TypeResolver.from_descriptor(self.descriptor).type_sig()

    def to_dict(self) -> dict:
        return {
            "descriptor": self.descriptor,
            "seed": self.seed,
            "budget": self.budget,
            "lineage": [asdict(op) if isinstance(op, LineageOp) else op for op in self.lineage],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Recipe":
        lineage = [LineageOp(**op) for op in d.get("lineage", [])]
        return cls(descriptor=d["descriptor"], seed=d["seed"], budget=d["budget"], lineage=lineage)


def materialize_base(recipe: "Recipe"):
    """Replay the BASE input (no lineage applied)."""
    handler = TypeResolver.from_descriptor(recipe.descriptor)
    budget = GenerationBudget.from_dict(recipe.budget)
    return handler.generate(random.Random(recipe.seed), budget)


def _get_node(root, path):
    """Return the live sub-node at path (traverses list/dict only)."""
    node = root
    for seg in path:
        kind, key = seg[0], seg[1]
        if kind == "list":
            node = node[key]
        else:  # "dict"
            node = node[decode(key)]
    return node


def _set_node(root, path, new_node):
    """Set the sub-node at path in place via its parent; path == [] replaces root."""
    if not path:
        return new_node
    parent = _get_node(root, path[:-1])
    kind, key = path[-1][0], path[-1][1]
    if kind == "list":
        parent[key] = new_node
    else:
        parent[decode(key)] = new_node
    return root


def _compute_op(op, old_node):
    """Pure: old node -> new node for one op."""
    name = op.op
    args = op.args
    if name == "scalar.replace":
        return decode(args["value"])
    if name == "list.insert":
        new = list(old_node); new.insert(args["index"], decode(args["value"])); return new
    if name == "list.delete":
        new = list(old_node); del new[args["index"]]; return new
    if name == "list.duplicate":
        new = list(old_node); new.insert(args["index"], new[args["index"]]); return new
    if name == "list.reverse":
        new = list(old_node); new.reverse(); return new
    if name == "list.empty":
        return []
    if name == "dict.drop_key":
        new = dict(old_node); new.pop(decode(args["key"]), None); return new
    if name == "dict.add_key":
        new = dict(old_node); new[decode(args["key"])] = decode(args["value"]); return new
    if name == "dict.corrupt_value":
        new = dict(old_node); new[decode(args["key"])] = decode(args["value"]); return new
    raise ValueError(f"unknown lineage op {name!r}")


def apply_lineage_op(root, op):
    """Apply one LineageOp at op.path (any depth). path == [] is the root case."""
    if not isinstance(op, LineageOp):
        op = LineageOp(**op)
    target = _get_node(root, op.path)
    return _set_node(root, op.path, _compute_op(op, target))


def materialize(recipe: "Recipe"):
    """Full replay: base generation + lineage applied in order."""
    value = materialize_base(recipe)
    for op in recipe.lineage:
        value = apply_lineage_op(value, op)
    return value
