import math

from edge_case_engine.codec import encode, decode, values_equal
from tests.user_type_fixtures import Color, Priority, Point, Box


def test_enum_member_roundtrip():
    assert values_equal(decode(encode(Color.GREEN)), Color.GREEN)
    assert decode(encode(Priority.HIGH)) is Priority.HIGH   # IntEnum, encoded as enum not int


def test_dataclass_roundtrip_including_nan_field():
    box = Box(label="x", size=float("nan"), tag=Color.RED)
    restored = decode(encode(box))
    assert values_equal(restored, box)          # nan-aware dataclass equality
    assert math.isnan(restored.size)
    assert restored.tag is Color.RED


def test_values_equal_dataclass_distinguishes_fields():
    assert values_equal(Point(1, 2), Point(1, 2)) is True
    assert values_equal(Point(1, 2), Point(1, 3)) is False
