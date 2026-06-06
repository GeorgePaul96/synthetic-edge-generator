from typing import Any, Callable, List


class InputMinimizer:
    """
    Given a function and an input tuple that crashes it with a specific error,
    attempts to find a shorter/simpler input that produces the same error signature.
    Uses a simple delta-debugging-style approach: try removing or simplifying
    individual elements of the input tuple.
    """

    @staticmethod
    def minimize(
        func: Callable,
        original_input: tuple,
        expected_error_sig: str,
        allowed_exceptions: tuple = (),
        max_attempts: int = 50,
    ) -> tuple:
        """
        Try to minimize original_input while still triggering expected_error_sig.
        Returns the smallest input found (may be the original if nothing simpler works).
        """
        from edge_case_engine.deduplicator import CrashDeduplicator

        best = original_input

        candidates = InputMinimizer._generate_candidates(original_input)

        for candidate in candidates[:max_attempts]:
            try:
                func(*candidate)
                # No exception — this candidate doesn't trigger the bug
            except Exception as e:
                if isinstance(e, allowed_exceptions):
                    continue  # allowed — not the crash we're looking for
                sig = CrashDeduplicator.signature(str(e))
                if sig == expected_error_sig:
                    # Same crash — compare sizes
                    if InputMinimizer._input_size(candidate) < InputMinimizer._input_size(best):
                        best = candidate

        return best

    @staticmethod
    def _input_size(inp: tuple) -> int:
        """Rough size metric: sum of string lengths of all elements."""
        return sum(len(str(e)) for e in inp)

    @staticmethod
    def _generate_candidates(original: tuple) -> List[tuple]:
        """Generate simpler candidate inputs to try."""
        candidates = []
        simple_values = [0, 0.0, 1, -1, "", None, False, True]

        for i, val in enumerate(original):
            for simple in simple_values:
                candidate = list(original)
                candidate[i] = simple
                candidates.append(tuple(candidate))

        return candidates
