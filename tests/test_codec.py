import math

from edge_case_engine.codec import encode, decode, values_equal


def test_roundtrip_specials_and_containers():
    value = {"a": [float("nan"), float("inf"), -1], 2: (b"x", {1, 2})}
    restored = decode(encode(value))
    assert values_equal(restored, value)
    # spot check nan survived
    assert math.isnan(restored["a"][0])


def test_values_equal_handles_nan():
    assert values_equal(float("nan"), float("nan")) is True
    assert values_equal(1, 1.0) is False   # type-strict
