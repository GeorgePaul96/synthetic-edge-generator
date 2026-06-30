from tests.user_type_fixtures import Color, Priority, Point, Box
from edge_case_engine.classref import class_to_ref, ref_to_class


def test_class_ref_roundtrip():
    for C in (Color, Priority, Point, Box):
        ref = class_to_ref(C)
        assert ":" in ref
        assert ref_to_class(ref) is C
