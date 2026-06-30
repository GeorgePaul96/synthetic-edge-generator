import random

from edge_case_engine.budget import GenerationBudget
from edge_case_engine.codec import values_equal
from type_handlers.enum_handler import EnumHandler
from type_handlers.dataclass_handler import DataclassHandler
from type_handlers.scalars import IntegerHandler
from tests.user_type_fixtures import Color, Point


def test_enum_handler_generates_member_deterministically():
    h = EnumHandler(Color)
    b = GenerationBudget()
    assert h.generate(random.Random(1), b) is h.generate(random.Random(1), b)
    assert h.generate(random.Random(1), b) in list(Color)
    assert h.descriptor() == {"k": "enum", "cls": "tests.user_type_fixtures:Color"}


def test_dataclass_handler_constructs_instance():
    h = DataclassHandler(Point, {"x": IntegerHandler(), "y": IntegerHandler()})
    b = GenerationBudget()
    v1 = h.generate(random.Random(2), b)
    v2 = h.generate(random.Random(2), GenerationBudget())
    assert isinstance(v1, Point) and values_equal(v1, v2)
    assert h.type_sig() == "dataclass[Point]"
    assert h.descriptor()["k"] == "dataclass" and "x" in h.descriptor()["fields"]


def test_dynamic_module_class_is_ref_roundtrippable(tmp_path):
    from synthedge.cli import load_module_from_path
    from edge_case_engine.classref import class_to_ref, ref_to_class
    target = tmp_path / "tgt.py"
    target.write_text("from dataclasses import dataclass\n@dataclass\nclass Q:\n    a: int\n")
    module = load_module_from_path(str(target))
    Q = module.Q
    assert ref_to_class(class_to_ref(Q)) is Q
