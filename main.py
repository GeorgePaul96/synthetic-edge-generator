from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.executor import FunctionExecutor
from edge_case_engine.discovery import TargetDiscovery
from edge_case_engine.corpus import CorpusManager

import operations
from type_handlers.float_handler import FloatHandler
from type_handlers.integer_handler import IntegerHandler

print("FILE EXECUTING")
def main():
    print("MAIN STARTED")
    engine = EdgeCaseEngine()
    executor = FunctionExecutor()
    corpus = CorpusManager()

    targets = TargetDiscovery.discover_modules([operations])

    max_iterations = 300

    for target in targets:
        print(f"Discovered targets: {targets}")
        print(f"\nFuzzing target: {target.name}")

        handlers = [
            FloatHandler(),
            IntegerHandler(),
        ]

        # Step 1: Initial seed generation
        test_cases = engine.generate(handlers)
        unique_cases = corpus.add_inputs(test_cases)

        # Add seeds to interesting pool
        for case in unique_cases:
            corpus.add_interesting_input(case, "seed")

        iteration = 0

        while iteration < max_iterations:

            seed_input = corpus.get_interesting_input()

            if seed_input is None:
                break

            # Step 2: Mutate seed
            mutated_cases = engine.mutation_engine.mutate(seed_input)

            if not isinstance(mutated_cases, list):
                mutated_cases = [mutated_cases]

            # Step 3: Execute
            results = executor.execute(target.function, mutated_cases)

            for result in results:

                # Step 4: Learn from coverage
                if result.new_path:
                    corpus.add_interesting_input(
                        result.input,
                        result.coverage_id
                    )
                    print("New path discovered!")

                # Step 5: Record crashes
                if result.error is not None:
                    corpus.record_crash(
                        result.input,
                        str(result.error),
                        result.severity
                    )
                    print("Crash detected!")

            iteration += 1
        print(f"Discovered targets: {targets}")
        print(f"Completed {iteration} iterations")



main()