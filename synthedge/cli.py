import argparse
import importlib.util
import os
import sys
import types
import typing
import random

from edge_case_engine.engine import EdgeCaseEngine
from edge_case_engine.executor import FunctionExecutor
from edge_case_engine.discovery import TargetDiscovery
from edge_case_engine.corpus import CorpusManager
from edge_case_engine.deduplicator import CrashDeduplicator
from edge_case_engine.budget import GenerationBudget
from edge_case_engine.recipe import Recipe
from type_handlers.resolver import TypeResolver
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


def run_fuzzer(module_path: str, iterations: int = 300, verbose: bool = False, seed=None) -> dict:
    """
    Fuzz all @fuzz_contract functions in the given module using the generation-based engine.
    Returns a summary dict: {target_name: {iterations, crashes_found}}.
    Deterministic for a fixed `seed`.
    """
    module = load_module_from_path(module_path)
    targets = TargetDiscovery.discover_modules([module])

    if not targets:
        print(f"No @fuzz_contract targets found in {module_path}")
        print("Tip: decorate your functions with @fuzz_contract from edge_case_engine.contracts")
        return {}

    if seed is None:
        seed = random.randrange(2 ** 63)
    master_rng = random.Random(seed)
    budget = GenerationBudget()

    module_abs = os.path.abspath(module_path)
    module_dir = os.path.dirname(module_abs)

    engine = EdgeCaseEngine()
    executor = FunctionExecutor()
    corpus = CorpusManager(corpus_dir=os.path.join(module_dir, "corpus"),
                           root=os.path.join(module_dir, ".synthedge"))
    summary = {}

    for target in targets:
        if verbose:
            print(f"\nFuzzing: {target.name}({', '.join(target.parameters)})")

        try:
            annotations = typing.get_type_hints(target.function)
        except Exception:
            annotations = {}

        handlers = [TypeResolver.resolve(annotations.get(p, None)) for p in target.parameters]
        if not handlers:
            summary[target.name] = {"iterations": iterations, "crashes_found": 0}
            continue

        pool = engine.generate_seeds(handlers, master_rng, budget,
                                     n_random=max(5, iterations // 3))
        crashes_found = 0

        for _ in range(iterations):
            if not pool:
                break
            base_input, base_recipes = pool[master_rng.randrange(len(pool))]

            h0 = handlers[0]
            mutator = engine.mutation.choose(h0, base_input[0], master_rng)
            if mutator is None:
                continue
            new_v0, op = mutator.mutate(h0, base_input[0], master_rng, budget, path=[])
            mutated = (new_v0,) + tuple(base_input[1:])

            new_recipes = [Recipe.from_dict(base_recipes[0].to_dict())] + list(base_recipes[1:])
            new_recipes[0].lineage = list(base_recipes[0].lineage) + [op]

            results = executor.execute(target.function, [mutated])
            for result in results:
                exc = (None if result.error is None
                       else f"{type(result.error).__name__}: {result.error}")
                env = corpus.make_envelope(new_recipes[0], mutated[0],
                                           artifacts={"exception": exc,
                                                      "coverage": result.coverage_id,
                                                      "output": None})
                if result.new_path:
                    pool.append((mutated, new_recipes))
                    corpus.save_interesting(env)
                if result.error is not None:
                    corpus.save_crash(env)
                    corpus.record_crash(list(mutated), exc, result.severity)
                    crashes_found += 1

        summary[target.name] = {"iterations": iterations, "crashes_found": crashes_found}

    # Deduplicate + export (legacy crash store feeds the pytest exporter)
    raw_crashes = corpus.get_crashes()
    deduped = []
    if raw_crashes:
        deduped = CrashDeduplicator.deduplicate(raw_crashes)
        corpus.write_deduplicated_crashes(deduped)
        print(f"\nDeduplication: {len(raw_crashes)} crashes -> {len(deduped)} unique")

    function_registry = {t.name: t.function for t in targets}
    output_path = os.path.join(module_dir, "synthedge_findings.py")
    n_written = PytestExporter.export(crashes=deduped, module_path=module_path,
                                      function_registry=function_registry, output_path=output_path)
    if n_written > 0:
        print(f"Pytest file written: {output_path} ({n_written} test cases)")

    print(f"synthedge seed={seed}")
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
    parser.add_argument("--seed", type=int, default=None,
                        help="Deterministic run seed (default: random)")

    args = parser.parse_args()

    print(f"synthedge v0.1.0 — fuzzing {args.module}")
    try:
        summary = run_fuzzer(args.module, iterations=args.iterations,
                             verbose=args.verbose, seed=args.seed)
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
