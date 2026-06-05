import time
from edge_case_engine.path_tracker import PathTracker

class ExecutionResult:
    def __init__(self, input_data, error, severity, coverage_id, new_path, exec_time_ms):
        self.input = input_data
        self.error = error
        self.severity = severity
        self.coverage_id = coverage_id
        self.new_path = new_path
        self.exec_time_ms = exec_time_ms

    def __repr__(self):
        return f"<ExecutionResult input={self.input} error={self.error} severity={self.severity} new_path={self.new_path} time={self.exec_time_ms:.3f}ms>"

class FunctionExecutor:
    def __init__(self):
        self.tracker = PathTracker()

    def execute(self, func, test_cases):
        results = []

        # Read the contract once for the function being fuzzed.
        # If no contract is present, default to None (treat all exceptions as crashes).
        contract = getattr(func, "__fuzz_contract__", None)

        for case in test_cases:
            self.tracker.start()
            error = None
            severity = "INFO"

            start_time = time.perf_counter()

            try:
                func(*case)
            except Exception as e:
                if contract is not None and isinstance(e, contract.allowed_exceptions):
                    # Exception is declared as expected behavior — not a crash.
                    # Leave error=None and severity="INFO" so the caller skips recording it.
                    pass
                else:
                    # No contract, or exception is not in the allowed list — real crash.
                    error = e
                    severity = "HIGH"
            finally:
                exec_time_ms = (time.perf_counter() - start_time) * 1000
                self.tracker.stop()

            coverage_id = self.tracker.compute_path_id()
            new_path = self.tracker.is_new_path(coverage_id)

            results.append(
                ExecutionResult(
                    case, error, severity, coverage_id, new_path, exec_time_ms
                )
            )
        return results