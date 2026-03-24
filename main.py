from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.executor import FunctionExecutor
from edge_case_engine.discovery import TargetDiscovery
from edge_case_engine.corpus import CorpusManager
from edge_case_engine.scheduler import PowerScheduler # NEW IMPORT

import operations
from type_handlers.float_handler import FloatHandler
from type_handlers.integer_handler import IntegerHandler

def main():
    print("MAIN STARTED")
    engine = EdgeCaseEngine()
    executor = FunctionExecutor()
    corpus = CorpusManager()
    scheduler = PowerScheduler() # NEW INSTANCE

    targets = TargetDiscovery.discover_modules([operations])
    max_iterations = 300

    for target in targets:
        print(f"\nFuzzing target: {target.name}")

        handlers = [FloatHandler(), IntegerHandler()]

        # Step 1: Initial seed generation
        test_cases = engine.generate(handlers)
        unique_cases = corpus.add_inputs(test_cases)

        # Add seeds to interesting pool (Default energy of 1.0)
        for case in unique_cases:
            corpus.add_interesting_input(case, coverage_id="seed")

        iteration = 0

        while iteration < max_iterations:
            
            # Step 2: Coverage-Guided Prioritization (Energy-weighted selection)
            interesting_pool = corpus.get_all_interesting_inputs()
            if not interesting_pool:
                break
                
            seed_input, energy = scheduler.choose_next_seed(interesting_pool)

            # Step 3: Havoc Mutation Scheduling
            stack_depth = scheduler.determine_mutation_stack_depth(energy)
            mutated_cases = engine.mutation.havoc_mutate([seed_input], stack_depth)

            if not isinstance(mutated_cases, list):
                mutated_cases = [mutated_cases]

            # Step 4: Execute
            results = executor.execute(target.function, mutated_cases)

            for result in results:
                # Update global edge frequencies
                scheduler.update_frequencies(result.coverage_id)

                # Step 5: Learn from coverage
                if result.new_path:
                    # Calculate evolutionary energy for the new discovery
                    new_energy = scheduler.calculate_energy(result.exec_time_ms, result.coverage_id)
                    
                    corpus.add_interesting_input(
                        result.input,
                        result.coverage_id,
                        energy=new_energy,
                        exec_time_ms=result.exec_time_ms
                    )
                    print(f"New path discovered! (Energy: {new_energy:.1f}, Depth: {stack_depth})")

                # Step 6: Record crashes
                if result.error is not None:
                    corpus.record_crash(
                        result.input,
                        str(result.error),
                        result.severity
                    )

            iteration += 1

        print(f"Completed {iteration} iterations on {target.name}")

if __name__ == "__main__":
    main()