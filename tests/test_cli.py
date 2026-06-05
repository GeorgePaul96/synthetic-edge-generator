"""
Tests for the synthedge CLI entry point.

Verifies that run_fuzzer() correctly discovers and fuzzes @fuzz_contract
functions, returns the expected summary structure, and gracefully handles
modules with no targets.
"""

import os
import sys
import unittest

# Ensure the project root is on the path so imports resolve
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from synthedge.cli import run_fuzzer, load_module_from_path


# Path to operations.py in the project root
_OPERATIONS_PATH = os.path.join(_PROJECT_ROOT, "operations.py")

# Expected targets in operations.py
_EXPECTED_TARGETS = {"add", "divide", "multiply", "format_ratio"}


class TestRunFuzzer(unittest.TestCase):

    def test_returns_dict_with_all_four_targets(self):
        """run_fuzzer on operations.py must return a dict keyed by all 4 targets."""
        summary = run_fuzzer(_OPERATIONS_PATH)
        self.assertIsInstance(summary, dict)
        self.assertEqual(set(summary.keys()), _EXPECTED_TARGETS,
                         f"Expected targets {_EXPECTED_TARGETS}, got {set(summary.keys())}")

    def test_each_target_has_iterations_field(self):
        """Every entry in the summary must have an 'iterations' key."""
        summary = run_fuzzer(_OPERATIONS_PATH)
        for name, stats in summary.items():
            self.assertIn("iterations", stats,
                          f"Target '{name}' missing 'iterations' key")

    def test_each_target_has_crashes_found_field(self):
        """Every entry in the summary must have a 'crashes_found' key."""
        summary = run_fuzzer(_OPERATIONS_PATH)
        for name, stats in summary.items():
            self.assertIn("crashes_found", stats,
                          f"Target '{name}' missing 'crashes_found' key")

    def test_crash_count_is_non_negative(self):
        """crashes_found for every target must be >= 0 (fuzzer ran without error)."""
        summary = run_fuzzer(_OPERATIONS_PATH)
        for name, stats in summary.items():
            self.assertGreaterEqual(stats["crashes_found"], 0,
                                    f"Target '{name}' has negative crashes_found")

    def test_iterations_is_positive(self):
        """iterations for every target must be > 0."""
        summary = run_fuzzer(_OPERATIONS_PATH)
        for name, stats in summary.items():
            self.assertGreater(stats["iterations"], 0,
                               f"Target '{name}' ran 0 iterations")

    def test_no_fuzz_contract_functions_returns_empty_dict(self):
        """A module with no @fuzz_contract functions must return {}."""
        # Use this test file itself — it has no @fuzz_contract decorators
        summary = run_fuzzer(os.path.abspath(__file__))
        self.assertEqual(summary, {},
                         "Module with no @fuzz_contract targets should return {}")

    def test_load_module_from_path_loads_operations(self):
        """load_module_from_path must successfully load operations.py as a module."""
        module = load_module_from_path(_OPERATIONS_PATH)
        self.assertIsNotNone(module)
        # The 4 functions should be accessible as attributes
        for func_name in _EXPECTED_TARGETS:
            self.assertTrue(hasattr(module, func_name),
                            f"Loaded module missing expected function '{func_name}'")

    def test_load_module_exposes_fuzz_contract_attribute(self):
        """Functions loaded via load_module_from_path must retain __fuzz_contract__."""
        module = load_module_from_path(_OPERATIONS_PATH)
        for func_name in _EXPECTED_TARGETS:
            func = getattr(module, func_name)
            self.assertTrue(hasattr(func, "__fuzz_contract__"),
                            f"Function '{func_name}' missing __fuzz_contract__ after load")


if __name__ == "__main__":
    unittest.main()
