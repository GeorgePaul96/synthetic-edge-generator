from edge_case_engine.budget import GenerationBudget


def test_child_shares_accountant_and_decrements_depth():
    b = GenerationBudget(max_depth=3, max_total_nodes=5)
    c = b.child()
    assert c.max_depth == 2
    assert b.spend(3) is True
    assert c.spend(2) is True          # shared pool: 5 - 3 - 2 = 0
    assert c.spend(1) is False         # exhausted
    assert b.spend(1) is False


def test_depth_exhausted_and_roundtrip():
    b = GenerationBudget(max_depth=0)
    assert b.depth_exhausted() is True
    assert GenerationBudget.from_dict(b.to_dict()).max_string_length == b.max_string_length
