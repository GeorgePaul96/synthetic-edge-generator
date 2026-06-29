import random

from edge_case_engine.rng import derive_child


def test_child_is_deterministic_from_parent_seed():
    a = derive_child(random.Random(7)).random()
    b = derive_child(random.Random(7)).random()
    assert a == b


def test_sequential_children_differ():
    parent = random.Random(7)
    first = derive_child(parent).random()
    second = derive_child(parent).random()
    assert first != second   # parent state advanced between draws
