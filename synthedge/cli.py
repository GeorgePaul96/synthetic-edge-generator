import argparse
import importlib.util
import os
import sys
import types
import typing

from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.executor import FunctionExecutor
from edge_case_engine.discovery import TargetDiscovery
from edge_case_engine.corpus import CorpusManager
from edge_case_engine.scheduler import PowerScheduler
from edge_case_engine.deduplicator import CrashDeduplicator
from type_handlers.registry import HandlerRegistry
from synthedge.exporter import PytestExporter


def load_module_from_path(path: str) -> types.ModuleType:
    """Load a Python file as a module by absolute/relative path."""
    spec = importlib.util.spec_from_file_location("_synthedge_target", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load module from: {path}")
    module = importlib.util.module_from_spec(spec)
    module_key = f"_synthedge_target_{os.path.abspath(path)}"
    sys.modules[module_key] = module
    spec.loader.exec_module(module)
    return module


def run_fuzzer(module_path: str, iterations: int = 300, verbose: bool = False) -> dict:
    """
    Fuzz all @fuzz_contract functions in the given module.
    Returns a summary dict: {target_name: {iterations, crashes_found}}
    """
    module = load_module_from_path(module_path)
    targets = TargetDiscovery.discover_modules([module])

    if not targets:
        print(f"No @fuzz_contract targets found in {module_path}")
        print("Tip: decorate your functions with @fuzz_contract from edge_case_engine.contracts")
        return {}

    module_abs = os.path.abspath(module_path)
    module_dir = os.path.dirname(module_abs)

    engine = EdgeCaseEngine()
    executor = FunctionExecutor()
    corpus = CorpusManager(corpus_dir=os.path.join(module_dir, "corpus"))
    scheduler = PowerScheduler()
    summary = {}

    for target in targets:
        if verbose:
            print(f"\nFuzzing: {target.name}({', '.join(target.parameters)})")

        annotations = {}
        try:
            annotations = typing.get_type_hints(target.function)
        except Exception:
            pass

        handlers = HandlerRegistry.handlers_for_params(target.parameters, annotations)
        test_cases = engine.generate(handlers)
        unique_cases = corpus.add_inputs(test_cases)

        for case in unique_cases:
            corpus.add_interesting_input(case, coverage_id="seed")

        # If no new unique cases (corpus already seen them all), re-seed from all
        # generated cases so the fuzzer pool is never empty.
        if not corpus.get_all_interesting_inputs():
            for case in test_cases:
                corpus.add_interesting_input(case, coverage_id="seed")

        crashes_found = 0
        iterations_done = 0

        for i in range(iterations):
            interesting_pool = corpus.get_all_interesting_inputs()
            if not interesting_pool:
                break

            seed_input, energy = scheduler.choose_next_seed(interesting_pool)
            stack_depth = scheduler.determine_mutation_stack_depth(energy)
            mutated_cases = engine.mutation.havoc_mutate([seed_input], stack_depth)

            if not isinstance(mutated_cases, list):
                mutated_cases = [mutated_cases]

            results = executor.execute(target.function, mutated_cases)

            for result in results:
                scheduler.update_frequencies(result.coverage_id)
                if result.new_path:
                    new_energy = scheduler.calculate_energy(result.exec_time_ms, result.coverage_id)
                    corpus.add_interesting_input(result.input, result.coverage_id,
                                                 energy=new_energy, exec_time_ms=result.exec_time_ms)
                    if verbose:
                        print(f"  New path (energy={new_energy:.1f})")
                if result.error is not None:
                    corpus.record_crash(
                        result.input,
                        f"{type(result.error).__name__}: {result.error}",
                        result.severity,
                    )
                    crashes_found += 1

            iterations_done = i + 1

        summary[target.name] = {"iterations": iterations_done, "crashes_found": crashes_found}

    # Deduplication pass — collapse identical crashes to their minimal representative
    raw_crashes = corpus.get_crashes()
    deduped = []
    if raw_crashes:
        deduped = CrashDeduplicator.deduplicate(raw_crashes)
        corpus.write_deduplicated_crashes(deduped)
        print(f"\nDeduplication: {len(raw_crashes)} crashes → {len(deduped)} unique")

    # Build function registry for the exporter
    function_registry = {t.name: t.function for t in targets}

    # Export crashes as a pytest file next to the target module
    output_path = os.path.join(module_dir, "synthedge_findings.py")
    n_written = PytestExporter.export(
        crashes=deduped,
        module_path=module_path,
        function_registry=function_registry,
        output_path=output_path,
    )
    if n_written > 0:
        print(f"Pytest file written: {output_path} ({n_written} test cases)")

    return summary


def print_summary(summary: dict, corpus_path: str = "corpus/crashes.json") -> None:
    print("\n" + "=" * 50)
    print("SYNTHEDGE RESULTS")
    print("=" * 50)
    total_crashes = 0
    for name, stats in summary.items():
        crashes = stats["crashes_found"]
        total_crashes += crashes
        status = "CRASHES FOUND" if crashes > 0 else "Clean"
        print(f"  {name:30s} {stats['iterations']:4d} iters  {crashes:4d} crashes  [{status}]")
    print("=" * 50)
    print(f"  Total real crashes: {total_crashes}")
    if total_crashes == 0:
        print("  No unexpected crashes found. Your functions handled all edge cases.")
    else:
        print(f"  See {corpus_path} for details.")


def main():
    parser = argparse.ArgumentParser(
        prog="synthedge",
        description="Automatically find inputs that break your Python functions",
    )
    parser.add_argument("module", help="Path to a Python file containing @fuzz_contract functions")
    parser.add_argument("-n", "--iterations", type=int, default=300,
                        help="Fuzzing iterations per target (default: 300)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show new paths as they are discovered")

    args = parser.parse_args()

    print(f"synthedge v0.1.0 — fuzzing {args.module}")
    try:
        summary = run_fuzzer(args.module, iterations=args.iterations, verbose=args.verbose)
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f"Error: {e}")
    except (ImportError, Exception) as e:
        sys.exit(f"Error loading module: {e}")

    if summary:
        corpus_path = os.path.join(
            os.path.dirname(os.path.abspath(args.module)), "corpus", "crashes.json"
        )
        print_summary(summary, corpus_path=corpus_path)


if __name__ == "__main__":
    main()
