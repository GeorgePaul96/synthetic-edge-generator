from edge_case_engine.path_tracker import PathTracker


class ExecutionResult:

    def __init__(self, input_data, error, severity, coverage_id, new_path):
        self.input = input_data
        self.error = error
        self.severity = severity
        self.coverage_id = coverage_id
        self.new_path = new_path


class FunctionExecutor:

    def __init__(self):

        self.tracker = PathTracker()

    def execute(self, func, test_cases):

        results = []

        for case in test_cases:

            self.tracker.start()

            error = None
            severity = "INFO"

            try:
                func(*case)

            except Exception as e:
                error = e
                severity = "HIGH"

            finally:
                self.tracker.stop()

            coverage_id = self.tracker.compute_path_id()

            new_path = self.tracker.is_new_path(coverage_id)

            results.append(
                ExecutionResult(
                    case,
                    error,
                    severity,
                    coverage_id,
                    new_path
                )
            )

        return results