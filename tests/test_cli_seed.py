from synthedge.cli import run_fuzzer


def test_run_fuzzer_is_deterministic_with_seed(tmp_path):
    target = tmp_path / "t.py"
    target.write_text(
        "from edge_case_engine.contracts import fuzz_contract\n"
        "@fuzz_contract(allowed_exceptions=())\n"
        "def f(xs):\n"
        "    return sum(xs)\n"
    )
    s1 = run_fuzzer(str(target), iterations=30, seed=123)
    s2 = run_fuzzer(str(target), iterations=30, seed=123)
    assert s1 == s2
