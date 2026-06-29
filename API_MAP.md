# API_MAP.md

No HTTP/network API. This is the internal Python module/class surface — the contract between
components. Signatures are current as of the merged tree.

## CLI / orchestration — [synthedge/cli.py](synthedge/cli.py)

```python
load_module_from_path(path: str) -> ModuleType        # dynamic import of a target file
run_fuzzer(module_path: str, iterations: int = 300, verbose: bool = False) -> dict
        # full pipeline; returns {target_name: {"iterations": int, "crashes_found": int}}
print_summary(summary: dict, corpus_path: str = "corpus/crashes.json") -> None
main()                                                  # argparse: <module> [-n N] [-v]
# console entry: `synthedge` → synthedge.cli:main  (pyproject.toml)
```

## Decorator & contract — [contracts.py](edge_case_engine/contracts.py)

```python
@fuzz_contract(allowed_exceptions: tuple = ())          # attaches __fuzz_contract__
@dataclass FuzzContract:
    allowed_exceptions: tuple = ()
    crash_exceptions: tuple = (MemoryError, SystemError, RuntimeError)
```

## Discovery — [discovery.py](edge_case_engine/discovery.py)

```python
@dataclass(frozen=True) FuzzTarget:
    function: Callable; name: str; module: str; parameters: tuple[str,...]; contract: dict
class TargetDiscovery:
    CONTRACT_ATTR = "__fuzz_contract__"
    @classmethod discover_module(module) -> list[FuzzTarget]
    @classmethod discover_modules(modules: list) -> list[FuzzTarget]
```

## Input generation

```python
# type_handlers/registry.py
class HandlerRegistry:
    _TYPE_MAP = {float: FloatHandler, int: IntegerHandler, str: StringHandler, bool: BoolHandler}
    @classmethod handlers_for_params(parameters: tuple, annotations: dict) -> list
        # one handler per param by type hint; FloatHandler fallback for unknown/unannotated

# type_handlers/*.py  (FloatHandler, IntegerHandler, StringHandler, BoolHandler, NoneHandler)
class <Type>Handler:
    generate_edge_cases() -> list

# edge_case_engine/engine.py
class EdgeCaseEngine:
    self.combinatorial: CombinatorialGenerator; self.mutation: MutationEngine  # from mutation.py
    generate(handlers: list) -> list[tuple]      # product + 1 mutation pass, de-duped

# edge_case_engine/combinatorial.py
class CombinatorialGenerator:
    generate(handler_cases: list[list]) -> list[tuple]
```

## Mutation — [mutation.py](edge_case_engine/mutation.py) (USED)

```python
class MutationEngine:
    mutate(test_cases) -> list[tuple]                       # 1 random mutation/case, cap 50
    havoc_mutate(test_cases, stack_depth=1) -> list[tuple]  # stack_depth mutations/case, cap 50
# edge_case_engine/mutation_engine.py — UNUSED numeric variant (same class name):
#   mutate_number / mutate_case / mutate_cases
```

## Execution & coverage

```python
# edge_case_engine/executor.py
class ExecutionResult:
    input; error; severity; coverage_id; new_path; exec_time_ms
class FunctionExecutor:
    self.tracker: PathTracker
    execute(func, test_cases) -> list[ExecutionResult]
        # reads func.__fuzz_contract__; allowed_exceptions => not a crash (error=None, INFO)

# edge_case_engine/path_tracker.py
class PathTracker:                       # _TOOL_ID = 3, name "synthedge"
    start() / stop()                     # sys.monitoring (3.12+) else sys.settrace
    compute_path_id() -> str             # sha256 of sorted "file:line" set (stdlib/site-pkgs filtered)
    is_new_path(path_id) -> bool
```

## Scheduling — [scheduler.py](edge_case_engine/scheduler.py)

```python
class PowerScheduler:
    global_edge_frequencies: dict[str, int]
    update_frequencies(coverage_id) -> None
    calculate_energy(exec_time_ms: float, coverage_id: str) -> float        # >= 1.0
    choose_next_seed(interesting_inputs: list[dict]) -> tuple[Any, float]   # roulette by energy
    determine_mutation_stack_depth(energy: float) -> int                    # randint(1, min(16, energy//10))
```

## Persistence — [corpus.py](edge_case_engine/corpus.py)

```python
class CorpusManager:
    __init__(corpus_dir="corpus")
    add_inputs(test_cases) -> list                          # sha256-dedupe → inputs.json
    add_interesting_input(test_input, coverage_id, energy=1.0, exec_time_ms=0.0) -> None  # in-memory
    get_all_interesting_inputs() -> list
    record_crash(test_input, error, severity) -> None       # append → crashes.json
    get_crashes() -> list                                   # read crashes.json
    write_deduplicated_crashes(crashes: list) -> None       # overwrite crashes.json
```

## Dedup, minimize, export

```python
# edge_case_engine/deduplicator.py
class CrashDeduplicator:
    @staticmethod signature(error_str) -> str               # normalize ('<type>', <N>, <addr>)
    @staticmethod deduplicate(crashes: list[dict]) -> list[dict]   # 1 per signature, shortest input

# edge_case_engine/minimizer.py
class InputMinimizer:
    @staticmethod minimize(func, original_input: tuple, expected_error_sig: str,
                           allowed_exceptions=(), max_attempts=50) -> tuple

# synthedge/exporter.py
class PytestExporter:
    @staticmethod export(crashes: list[dict], module_path: str,
                         function_registry: dict[str, Callable], output_path: str) -> int
        # returns number of test cases written to synthedge_findings.py
```

## Demo targets — [operations.py](operations.py)

```python
@fuzz_contract(allowed_exceptions=(ValueError,))            divide(a, b); add(a, b); multiply(a, b)
@fuzz_contract(allowed_exceptions=(ValueError, TypeError))  format_ratio(numerator: float, label: str)
```

> **Add a target:** write the function, decorate `@fuzz_contract`, run `synthedge <file.py>`.
> **Add an input domain:** new handler class with `generate_edge_cases()` in `type_handlers/`,
> register it in [registry.py](type_handlers/registry.py)'s `_TYPE_MAP`.
