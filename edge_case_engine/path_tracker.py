import sys
import hashlib
from typing import Set


class PathTracker:
    """
    Tracks executed code paths during fuzz execution.
    Uses sys.settrace for lightweight coverage tracking.
    """

    def __init__(self):
        self.current_path: Set[int] = set()
        self.known_paths: Set[str] = set()

    # -----------------------------
    # Trace Function
    # -----------------------------

    def _trace(self, frame, event, arg):

        if event == "line":
            lineno = frame.f_lineno
            self.current_path.add(lineno)

        return self._trace

    # -----------------------------
    # Execution Control
    # -----------------------------

    def start(self):

        self.current_path.clear()
        sys.settrace(self._trace)

    def stop(self):

        sys.settrace(None)

    # -----------------------------
    # Path Analysis
    # -----------------------------

    def compute_path_id(self) -> str:

        ordered = sorted(self.current_path)

        signature = "-".join(map(str, ordered))

        return hashlib.sha256(signature.encode()).hexdigest()

    def is_new_path(self, path_id: str) -> bool:

        if path_id in self.known_paths:
            return False

        self.known_paths.add(path_id)
        return True