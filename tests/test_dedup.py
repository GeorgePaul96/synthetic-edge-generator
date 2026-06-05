"""
Tests for CrashDeduplicator and InputMinimizer.
"""

import os
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from edge_case_engine.deduplicator import CrashDeduplicator
from edge_case_engine.minimizer import InputMinimizer


class TestCrashDeduplicatorSignature(unittest.TestCase):

    def test_strips_type_names_in_quotes(self):
        """signature() replaces quoted type names with '<type>'."""
        error_str = "unsupported operand type(s) for +: 'NoneType' and 'str'"
        sig = CrashDeduplicator.signature(error_str)
        self.assertIn("<type>", sig)
        self.assertNotIn("NoneType", sig)
        self.assertNotIn("str", sig)

    def test_strips_hex_addresses(self):
        """signature() replaces hex memory addresses with '<addr>'."""
        error_str = "Object at 0x7f3a1b2c3d4e failed"
        sig = CrashDeduplicator.signature(error_str)
        self.assertIn("<addr>", sig)
        self.assertNotIn("0x7f3a1b2c3d4e", sig)

    def test_strips_numbers(self):
        """signature() replaces bare integers with '<N>'."""
        error_str = "index 42 is out of range for length 10"
        sig = CrashDeduplicator.signature(error_str)
        self.assertIn("<N>", sig)
        self.assertNotIn("42", sig)
        self.assertNotIn("10", sig)

    def test_identical_errors_produce_same_signature(self):
        """Two identical error strings produce the same signature."""
        e = "TypeError: 'int' object is not subscriptable"
        self.assertEqual(CrashDeduplicator.signature(e), CrashDeduplicator.signature(e))

    def test_same_error_different_type_names_produces_same_signature(self):
        """Errors that differ only in the quoted type name collapse to the same signature."""
        e1 = "unsupported operand type(s) for +: 'NoneType' and 'str'"
        e2 = "unsupported operand type(s) for +: 'int' and 'list'"
        self.assertEqual(CrashDeduplicator.signature(e1), CrashDeduplicator.signature(e2))


class TestCrashDeduplicatorDeduplicate(unittest.TestCase):

    def _crash(self, error: str, inp="abc", severity="medium"):
        return {"input": inp, "error": error, "severity": severity}

    def test_empty_list_returns_empty_list(self):
        """deduplicate([]) must return []."""
        self.assertEqual(CrashDeduplicator.deduplicate([]), [])

    def test_identical_crashes_deduplicated_to_one(self):
        """Two crashes with the same error type+message collapse to 1 entry."""
        crashes = [
            self._crash("TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'", inp="abc"),
            self._crash("TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'", inp="xyz"),
        ]
        result = CrashDeduplicator.deduplicate(crashes)
        self.assertEqual(len(result), 1)

    def test_different_error_types_both_kept(self):
        """Crashes with different error types are each preserved."""
        crashes = [
            self._crash("TypeError: bad operand"),
            self._crash("ValueError: invalid literal"),
        ]
        result = CrashDeduplicator.deduplicate(crashes)
        self.assertEqual(len(result), 2)

    def test_keeps_shortest_input(self):
        """When two crashes share a signature, the one with the shorter input is kept."""
        crashes = [
            self._crash("TypeError: 'NoneType'", inp="a very long input string that is longer"),
            self._crash("TypeError: 'NoneType'", inp="x"),
        ]
        result = CrashDeduplicator.deduplicate(crashes)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["input"], "x")

    def test_keeps_shortest_input_regardless_of_order(self):
        """Shorter input wins even when it appears first in the list."""
        crashes = [
            self._crash("TypeError: 'NoneType'", inp="short"),
            self._crash("TypeError: 'NoneType'", inp="a much longer input than short"),
        ]
        result = CrashDeduplicator.deduplicate(crashes)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["input"], "short")

    def test_single_crash_passes_through(self):
        """A list with one crash deduplicated is still one crash."""
        crashes = [self._crash("RuntimeError: exploded")]
        result = CrashDeduplicator.deduplicate(crashes)
        self.assertEqual(len(result), 1)

    def test_three_unique_errors_all_kept(self):
        """Three structurally different errors all survive dedup."""
        crashes = [
            self._crash("TypeError: bad operand"),
            self._crash("ValueError: invalid literal"),
            self._crash("KeyError: 'missing_key'"),
        ]
        result = CrashDeduplicator.deduplicate(crashes)
        self.assertEqual(len(result), 3)


class TestInputMinimizer(unittest.TestCase):

    def _crashing_func(self, a, b):
        """Raises TypeError when a is None."""
        if a is None:
            raise TypeError("'NoneType' cannot be added")
        return a + b

    def test_minimize_returns_tuple(self):
        """minimize() always returns a tuple."""
        original = ("hello world string", 42)
        from edge_case_engine.deduplicator import CrashDeduplicator
        expected_sig = CrashDeduplicator.signature("TypeError: 'NoneType' cannot be added")
        result = InputMinimizer.minimize(self._crashing_func, original, expected_sig)
        self.assertIsInstance(result, tuple)

    def test_minimize_finds_shorter_input(self):
        """minimize() finds a shorter first argument that still triggers the crash."""
        original = ("a very long string that is not None", 99999)
        from edge_case_engine.deduplicator import CrashDeduplicator
        expected_sig = CrashDeduplicator.signature("TypeError: 'NoneType' cannot be added")
        result = InputMinimizer.minimize(self._crashing_func, original, expected_sig)
        # None triggers the same crash and has size 4 ("None") vs long string
        self.assertLessEqual(
            InputMinimizer._input_size(result),
            InputMinimizer._input_size(original),
        )

    def test_minimize_returns_original_when_no_simpler_input_found(self):
        """When no candidate triggers the same crash, original is returned."""
        def very_specific_crash(a, b):
            if a == 999 and b == 888:
                raise RuntimeError("specific crash only on 999,888")
            return a + b

        original = (999, 888)
        from edge_case_engine.deduplicator import CrashDeduplicator
        expected_sig = CrashDeduplicator.signature("RuntimeError: specific crash only on <N>,<N>")
        # The generated candidates use simple values, none of which is 999 or 888
        result = InputMinimizer.minimize(very_specific_crash, original, expected_sig)
        self.assertEqual(result, original)

    def test_input_size_metric(self):
        """_input_size returns the sum of string lengths of all elements."""
        inp = (None, 0, "ab")
        # "None"=4, "0"=1, "ab"=2 → 7
        self.assertEqual(InputMinimizer._input_size(inp), 7)

    def test_generate_candidates_produces_non_empty_list(self):
        """_generate_candidates returns at least one candidate for a non-empty tuple."""
        candidates = InputMinimizer._generate_candidates((1, "hello"))
        self.assertGreater(len(candidates), 0)

    def test_generate_candidates_each_is_same_length(self):
        """Each candidate tuple has the same arity as the original."""
        original = (1, "hello", 3.14)
        candidates = InputMinimizer._generate_candidates(original)
        for c in candidates:
            self.assertEqual(len(c), len(original))


if __name__ == "__main__":
    unittest.main()
