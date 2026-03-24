import sys
import hashlib


class PathTracker:

    def __init__(self):
        self.current_path = set()
        self.known_paths = set()

    def _trace(self, frame, event, arg):

        if event == "line":
            filename = frame.f_code.co_filename
            lineno = frame.f_lineno

            self.current_path.add(f"{filename}:{lineno}")

        return self._trace

    def start(self):
        self.current_path.clear()
        sys.settrace(self._trace)

    def stop(self):
        sys.settrace(None)

    def compute_path_id(self):

        ordered = sorted(self.current_path)
        signature = "-".join(ordered)

        return hashlib.sha256(signature.encode()).hexdigest()

    def is_new_path(self, path_id):

        if path_id in self.known_paths:
            return False

        self.known_paths.add(path_id)
        return True