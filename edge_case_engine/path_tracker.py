import sys
import hashlib
import os
import sysconfig

_THIS_FILE = os.path.abspath(__file__)


def _use_monitoring() -> bool:
    """True if sys.monitoring (Python 3.12+) is available."""
    return hasattr(sys, "monitoring") and hasattr(sys.monitoring, "events")


def _stdlib_prefix() -> str:
    """Return the normalized stdlib directory prefix for this Python installation."""
    stdlib_path = sysconfig.get_paths().get("stdlib", "")
    return os.path.normcase(stdlib_path)


_STDLIB_PREFIX = _stdlib_prefix()


class PathTracker:
    # Use tool ID 3 — user slot (IDs 0-4 are user-assignable; 5 == OPTIMIZER_ID on 3.14)
    _TOOL_ID = 3
    _TOOL_NAME = "synthedge"

    def __init__(self):
        self.current_path = set()
        self.known_paths = set()
        self._use_fast = _use_monitoring()
        self._active = False
        self._owns_tool_id = False

        if self._use_fast:
            try:
                sys.monitoring.use_tool_id(self._TOOL_ID, self._TOOL_NAME)
                self._owns_tool_id = True
            except ValueError:
                # Slot already in use (e.g. nested PathTracker) — fall back to sys.settrace
                self._use_fast = False

    @staticmethod
    def _should_track(filename: str) -> bool:
        """Return True if the file should be included in path tracking."""
        if not filename or filename.startswith("<"):
            return False
        norm = os.path.normcase(filename)
        # Skip stdlib using the actual installation prefix (works on Windows too)
        if _STDLIB_PREFIX and norm.startswith(_STDLIB_PREFIX):
            return False
        # Skip installed packages
        if "site-packages" in norm:
            return False
        # Skip path_tracker.py itself (avoids capturing start()/stop() internals).
        # Compare against the known absolute path to avoid false-matches on files
        # like "test_path_tracker.py" that contain the substring.
        if os.path.normcase(_THIS_FILE) == norm:
            return False
        return True

    def _monitoring_line_callback(self, code, line_number):
        """Callback registered with sys.monitoring for LINE events."""
        if self._should_track(code.co_filename):
            self.current_path.add(f"{code.co_filename}:{line_number}")

    def _settrace_callback(self, frame, event, arg):
        """Fallback settrace handler for Python < 3.12."""
        if event == "line":
            filename = frame.f_code.co_filename
            if self._should_track(filename):
                self.current_path.add(f"{filename}:{frame.f_lineno}")
        return self._settrace_callback

    def start(self):
        self.current_path.clear()
        self._active = True
        if self._use_fast:
            sys.monitoring.register_callback(
                self._TOOL_ID,
                sys.monitoring.events.LINE,
                self._monitoring_line_callback,
            )
            sys.monitoring.set_events(self._TOOL_ID, sys.monitoring.events.LINE)
        else:
            sys.settrace(self._settrace_callback)

    def stop(self):
        if not self._active:
            return
        self._active = False
        if self._use_fast:
            sys.monitoring.set_events(self._TOOL_ID, 0)
            sys.monitoring.register_callback(
                self._TOOL_ID, sys.monitoring.events.LINE, None
            )
        else:
            sys.settrace(None)

    def compute_path_id(self) -> str:
        ordered = sorted(self.current_path)
        signature = "-".join(ordered)
        return hashlib.sha256(signature.encode()).hexdigest()

    def is_new_path(self, path_id: str) -> bool:
        if path_id in self.known_paths:
            return False
        self.known_paths.add(path_id)
        return True

    def __del__(self):
        """Clean up the tool ID when the tracker is garbage collected."""
        if self._owns_tool_id:
            try:
                sys.monitoring.set_events(self._TOOL_ID, 0)
                sys.monitoring.free_tool_id(self._TOOL_ID)
            except Exception:
                pass
