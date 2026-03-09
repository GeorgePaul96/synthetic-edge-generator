from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.executor import FunctionExecutor
from edge_case_engine.discovery import TargetDiscovery
from edge_case_engine.corpus import CorpusManager

import operations
from type_handlers.float_handler import FloatHandler
from type_handlers.integer_handler import IntegerHandler


def main():

    engine = EdgeCaseEngine()
    executor = FunctionExecutor()
    corpus = CorpusManager()

    targets = TargetDiscovery.discover_modules([operations])

    for target in targets:

        print(f"\nFuzzing target: {target.name}")

        handlers = [
            FloatHandler(),
            IntegerHandler(),
        ]

        test_cases = engine.generate(handlers)

        # Deduplicate via corpus
        unique_cases = corpus.add_inputs(test_cases)

        print(f"Generated: {len(test_cases)}")
        print(f"Unique new cases: {len(unique_cases)}")

        results = executor.execute(target.function, unique_cases)

        for result in results:
            if result.new_path:
                print("New path discovered!")
            if result.error is not None:    
                corpus.record_crash(
                    result.input,
                    str(result.error),
                    result.severity
                )

        print(f"Crashes recorded: {len(corpus.load_crashes())}")


if __name__ == "__main__":
    main()