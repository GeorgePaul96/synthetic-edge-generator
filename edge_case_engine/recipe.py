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


def apply_lineage_op(value, op):
    """Apply one LineageOp to the root value (Slice 1: path == [])."""
    if not isinstance(op, LineageOp):
        op = LineageOp(**op)
    name = op.op
    args = op.args
    if name == "scalar.replace":
        return decode(args["value"])
    if name == "list.insert":
        value = list(value)
        value.insert(args["index"], decode(args["value"]))
        return value
    if name == "list.delete":
        value = list(value)
        del value[args["index"]]
        return value
    if name == "list.duplicate":
        value = list(value)
        value.insert(args["index"], value[args["index"]])
        return value
    if name == "list.reverse":
        value = list(value)
        value.reverse()
        return value
    if name == "list.empty":
        return []
    if name == "dict.drop_key":
        value = dict(value)
        value.pop(decode(args["key"]), None)
        return value
    if name == "dict.add_key":
        value = dict(value)
        value[decode(args["key"])] = decode(args["value"])
        return value
    if name == "dict.corrupt_value":
        value = dict(value)
        value[decode(args["key"])] = decode(args["value"])
        return value
    raise ValueError(f"unknown lineage op {name!r}")


def materialize(recipe: "Recipe"):
    """Full replay: base generation + lineage applied in order."""
    value = materialize_base(recipe)
    for op in recipe.lineage:
        value = apply_lineage_op(value, op)
    return value
