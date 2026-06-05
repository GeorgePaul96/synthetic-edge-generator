"""
Tests for contract-aware crash filtering in FunctionExecutor.

Verifies that exceptions declared as allowed in @fuzz_contract are NOT
recorded as crashes, while unexpected exceptions and no-contract functions
still produce crash records.
"""

import unittest
from edge_case_engine.executor import FunctionExecutor
from edge_case_engine.contracts import fuzz_contract


# ---------------------------------------------------------------------------
# Helper functions used by the test cases
# ---------------------------------------------------------------------------

@fuzz_contract(allowed_exceptions=(ValueError,))
def func_raises_allowed(x):
    """Always raises ValueError — declared as allowed."""
    raise ValueError("expected error")


@fuzz_contract(allowed_exceptions=(ValueError,))
def func_raises_disallowed(x):
    """Always raises TypeError — NOT in the allowed list."""
    raise TypeError("unexpected error")


@fuzz_contract(allowed_exceptions=(ValueError,))
def func_no_raise(x):
    """Never raises — clean execution."""
    return x * 2


@fuzz_contract(allowed_exceptions=(ValueError,))
def func_mixed_batch(x):
    """Raises ValueError for even x (allowed), TypeError for odd x (disallowed)."""
    if x % 2 == 0:
        raise ValueError("allowed error for even input")
    else:
        raise TypeError("disallowed error for odd input")


@fuzz_contract(allowed_exceptions=())
def func_empty_allowed_list(x):
    """Contract specifies no allowed exceptions — any exception is a crash."""
    raise ValueError("not in allowed list")


def func_no_contract(x):
    """No @fuzz_contract decorator — all exceptions are crashes."""
    raise RuntimeError("bare exception")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestContractFiltering(unittest.TestCase):

    def setUp(self):
        self.executor = FunctionExecutor()

    def _run_single(self, func, arg=(1,)):
        """Execute func with a single test case and return the one result."""
        results = self.executor.execute(func, [arg])
        self.assertEqual(len(results), 1)
        return results[0]

    # ------------------------------------------------------------------
    # 1. Allowed exception → NOT a crash
    # ------------------------------------------------------------------
    def test_allowed_exception_not_recorded_as_crash(self):
        """ValueError raised by a function with allowed_exceptions=(ValueError,)
        must NOT set error on the result."""
        result = self._run_single(func_raises_allowed)
        self.assertIsNone(result.error,
            "Allowed exception should not be recorded as a crash (error must be None)")

    def test_allowed_exception_severity_is_info(self):
        """Result for an allowed exception should keep severity='INFO'."""
        result = self._run_single(func_raises_allowed)
        self.assertEqual(result.severity, "INFO",
            "Allowed exception should leave severity as INFO")

    # ------------------------------------------------------------------
    # 2. Disallowed exception → HIGH severity crash
    # ------------------------------------------------------------------
    def test_disallowed_exception_recorded_as_crash(self):
        """TypeError raised by a function whose contract only allows ValueError
        MUST be recorded as a crash."""
        result = self._run_single(func_raises_disallowed)
        self.assertIsNotNone(result.error,
            "Non-allowed exception must be recorded as a crash")
        self.assertIsInstance(result.error, TypeError)

    def test_disallowed_exception_severity_is_high(self):
        """Non-allowed exception must have severity='HIGH'."""
        result = self._run_single(func_raises_disallowed)
        self.assertEqual(result.severity, "HIGH",
            "Non-allowed exception must have HIGH severity")

    # ------------------------------------------------------------------
    # 3. No contract → all exceptions are crashes
    # ------------------------------------------------------------------
    def test_no_contract_exception_is_crash(self):
        """A function with no @fuzz_contract that raises must produce a crash."""
        result = self._run_single(func_no_contract)
        self.assertIsNotNone(result.error,
            "Exception from a no-contract function must be recorded as crash")
        self.assertEqual(result.severity, "HIGH",
            "No-contract exception must have HIGH severity")

    # ------------------------------------------------------------------
    # 4. Clean execution → zero crashes
    # ------------------------------------------------------------------
    def test_no_raise_produces_no_crash(self):
        """A function that does not raise must produce no crash record."""
        result = self._run_single(func_no_raise)
        self.assertIsNone(result.error)
        self.assertEqual(result.severity, "INFO")

    # ------------------------------------------------------------------
    # 5. Corpus crash count for contract-compliant behavior is zero
    # ------------------------------------------------------------------
    def test_corpus_records_zero_crashes_for_allowed_exceptions(self):
        """Running multiple allowed-exception cases must yield zero crash entries."""
        test_cases = [(1,), (2,), (3,), (4,), (5,)]
        results = self.executor.execute(func_raises_allowed, test_cases)

        crash_results = [r for r in results if r.error is not None]
        self.assertEqual(len(crash_results), 0,
            f"Expected 0 crash entries, got {len(crash_results)}")

    # ------------------------------------------------------------------
    # 6. Mixed batch: allowed + disallowed counted correctly
    # ------------------------------------------------------------------
    def test_mixed_batch_with_allowed_and_disallowed_exceptions(self):
        """A single batch where one function raises allowed exceptions (ValueError)
        on some inputs and disallowed exceptions (TypeError) on others. Only
        the disallowed exceptions should be recorded as crashes."""
        # func_mixed_batch raises ValueError (allowed) for even inputs,
        # and TypeError (disallowed) for odd inputs.
        test_cases = [(0,), (1,), (2,), (3,), (4,)]  # 0,2,4 are even; 1,3 are odd
        results = self.executor.execute(func_mixed_batch, test_cases)

        # Filter results
        crash_results = [r for r in results if r.error is not None]
        no_crash_results = [r for r in results if r.error is None]

        # Only 2 should be disallowed (TypeError for odd inputs 1, 3)
        self.assertEqual(len(crash_results), 2,
            f"Expected 2 disallowed (TypeError) exceptions as crashes, got {len(crash_results)}")
        # And 3 should be allowed (ValueError for even inputs 0, 2, 4)
        self.assertEqual(len(no_crash_results), 3,
            f"Expected 3 allowed (ValueError) exceptions not as crashes, got {len(no_crash_results)}")
        # All crash results should be TypeError
        for crash in crash_results:
            self.assertIsInstance(crash.error, TypeError,
                f"Expected TypeError in crash, got {type(crash.error)}")

    # ------------------------------------------------------------------
    # 7. Empty allowed_exceptions list → all exceptions are crashes
    # ------------------------------------------------------------------
    def test_empty_allowed_exceptions_list_records_all_as_crashes(self):
        """A function with allowed_exceptions=() (empty tuple) should record
        all exceptions as crashes, since nothing is allowed."""
        result = self._run_single(func_empty_allowed_list)
        self.assertIsNotNone(result.error,
            "Exception from empty allowed_exceptions must be recorded as crash")
        self.assertIsInstance(result.error, ValueError)
        self.assertEqual(result.severity, "HIGH",
            "Exception from empty allowed_exceptions must have HIGH severity")


if __name__ == "__main__":
    unittest.main()
