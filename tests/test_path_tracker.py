"""
Tests for PathTracker.

Design notes
------------
sys.monitoring (and the settrace fallback) captures LINE events for every
.py file that runs while tracking is active — including the test file itself.
To keep path IDs stable across two "identical" runs, all tracked function
calls are routed through a single fixed helper (_tracked_call) so that the
call-site line number is always the same.
"""
import unittest
from edge_case_engine.path_tracker import PathTracker


# ---------------------------------------------------------------------------
# Target functions (stable line numbers are important for determinism tests)
# ---------------------------------------------------------------------------

def _simple_add(x, y):
    return x + y


def _branch_fn(x):
    if x > 0:
        return "positive"
    else:
        return "non-positive"


# ---------------------------------------------------------------------------
# Helper: fixed call-site wrapper so line numbers are reproducible
# ---------------------------------------------------------------------------

def _tracked_call(tracker, fn, *args):
    """Start tracker, call fn(*args), stop tracker — all from one stable site."""
    tracker.start()
    fn(*args)           # ← call always happens at this same line
    tracker.stop()


class TestPathTrackerInit(unittest.TestCase):
    def setUp(self):
        self.tracker = PathTracker()

    def tearDown(self):
        self.tracker.stop()
        del self.tracker

    def test_initial_current_path_is_empty(self):
        self.assertEqual(len(self.tracker.current_path), 0)

    def test_initial_known_paths_is_empty(self):
        self.assertEqual(len(self.tracker.known_paths), 0)


class TestPathTrackerTracking(unittest.TestCase):
    def setUp(self):
        self.tracker = PathTracker()

    def tearDown(self):
        self.tracker.stop()
        del self.tracker

    def test_current_path_nonempty_after_start_call_stop(self):
        _tracked_call(self.tracker, _simple_add, 1, 2)
        self.assertGreater(len(self.tracker.current_path), 0)

    def test_current_path_cleared_on_new_start(self):
        """Path from first run must not leak into second run."""
        _tracked_call(self.tracker, _simple_add, 1, 2)
        path_run1 = frozenset(self.tracker.current_path)
        self.assertGreater(len(path_run1), 0)

        # start() must clear current_path before the second run
        _tracked_call(self.tracker, _simple_add, 3, 4)
        path_run2 = frozenset(self.tracker.current_path)

        # Run 2 should equal run 1 (same call site, same function body lines)
        # — crucially: it must NOT keep growing with every extra run
        self.assertEqual(path_run1, path_run2,
                         "current_path was not cleared between runs")

    def test_no_stdlib_lines_in_path(self):
        _tracked_call(self.tracker, _simple_add, 1, 2)
        for entry in self.tracker.current_path:
            self.assertNotIn("lib/python", entry,
                             f"stdlib line leaked into path: {entry}")
            self.assertNotIn("lib\\python", entry,
                             f"stdlib line leaked into path: {entry}")

    def test_no_site_packages_in_path(self):
        _tracked_call(self.tracker, _simple_add, 1, 2)
        for entry in self.tracker.current_path:
            self.assertNotIn("site-packages", entry,
                             f"site-packages line leaked into path: {entry}")


class TestComputePathId(unittest.TestCase):
    def setUp(self):
        self.tracker = PathTracker()

    def tearDown(self):
        self.tracker.stop()
        del self.tracker

    def test_compute_path_id_returns_64_char_hex(self):
        _tracked_call(self.tracker, _simple_add, 1, 2)
        path_id = self.tracker.compute_path_id()
        self.assertEqual(len(path_id), 64)
        # Must be valid hex — int() will raise if not
        int(path_id, 16)

    def test_identical_executions_produce_same_path_id(self):
        """Two runs of the same function via the same call site must yield the same ID."""
        _tracked_call(self.tracker, _simple_add, 10, 20)
        id1 = self.tracker.compute_path_id()

        _tracked_call(self.tracker, _simple_add, 10, 20)
        id2 = self.tracker.compute_path_id()

        self.assertEqual(id1, id2)

    def test_different_executions_produce_different_path_ids(self):
        """Two functions that take different branches must produce different IDs."""
        _tracked_call(self.tracker, _branch_fn, 1)    # takes x > 0 branch
        id_positive = self.tracker.compute_path_id()

        _tracked_call(self.tracker, _branch_fn, -1)   # takes else branch
        id_negative = self.tracker.compute_path_id()

        self.assertNotEqual(id_positive, id_negative)


class TestIsNewPath(unittest.TestCase):
    def setUp(self):
        self.tracker = PathTracker()

    def tearDown(self):
        self.tracker.stop()
        del self.tracker

    def test_first_call_returns_true(self):
        self.assertTrue(self.tracker.is_new_path("abc123"))

    def test_second_call_same_id_returns_false(self):
        self.tracker.is_new_path("abc123")
        self.assertFalse(self.tracker.is_new_path("abc123"))

    def test_different_ids_both_return_true_on_first_call(self):
        self.assertTrue(self.tracker.is_new_path("id_one"))
        self.assertTrue(self.tracker.is_new_path("id_two"))

    def test_known_paths_grows_with_new_ids(self):
        self.tracker.is_new_path("x")
        self.tracker.is_new_path("y")
        self.assertIn("x", self.tracker.known_paths)
        self.assertIn("y", self.tracker.known_paths)


class TestStopIdempotent(unittest.TestCase):
    def setUp(self):
        self.tracker = PathTracker()

    def tearDown(self):
        del self.tracker

    def test_stop_without_start_does_not_raise(self):
        """stop() before start() must be a safe no-op."""
        try:
            self.tracker.stop()
        except Exception as e:
            self.fail(f"stop() raised unexpectedly: {e}")

    def test_double_stop_does_not_raise(self):
        self.tracker.start()
        self.tracker.stop()
        try:
            self.tracker.stop()
        except Exception as e:
            self.fail(f"second stop() raised unexpectedly: {e}")


if __name__ == "__main__":
    unittest.main()
