# ARCHITECTURE.md

How **synthedge** works end to end. Companion to [PROJECT_MAP.md](PROJECT_MAP.md) (file inventory)
and [API_MAP.md](API_MAP.md) (class/method surface). User-facing summary: [README.md](README.md).

## What it is

An AFL-style, coverage-guided fuzzer for Python functions, plus a **pytest exporter**. Pure stdlib
core. The deliverable is not just "crashes found" but a drop-in `synthedge_findings.py` test file
containing minimized, deduplicated reproducers.

Pipeline stages: **discover → generate → evolve (fuzz) → deduplicate → minimize → export.**

## Entry points

- **`synthedge/cli.py`** — the product. `synthedge <module.py> [-n N] [-v]`. Implements the full
  pipeline including dedup + export. **Authoritative.**
- **`main.py`** — legacy demo harness fuzzing the hardcoded `operations` module. Runs the
  fuzz loop only (no dedup, no export). Superseded by the CLI; kept for reference.

## Full pipeline (CLI — `run_fuzzer`)

```
synthedge <module.py>                              synthedge/cli.py
  load_module_from_path(module)                    # dynamic import by file path
  targets = TargetDiscovery.discover_modules([m])  # functions with __fuzz_contract__
        │
        ▼  for each target:
  annotations = typing.get_type_hints(fn)
  handlers   = HandlerRegistry.handlers_for_params(params, annotations)   type_handlers/registry.py
  seeds      = EdgeCaseEngine.generate(handlers)   # combinatorial product + 1 mutation pass, deduped
  corpus.add_inputs(seeds)                         # sha256 dedupe → inputs.json; seed interesting pool
        │
        ▼  evolutionary loop (N iterations, default 300):
  seed, energy = PowerScheduler.choose_next_seed(pool)        # roulette by energy
  depth        = PowerScheduler.determine_mutation_stack_depth(energy)
  mutated      = MutationEngine.havoc_mutate([seed], depth)   edge_case_engine/mutation.py
  results      = FunctionExecutor.execute(fn, mutated)        edge_case_engine/executor.py
        │   └─ PathTracker traces executed lines (sys.monitoring 3.12+ / settrace) → sha256 path id
        │      executor is CONTRACT-AWARE: exceptions in allowed_exceptions are NOT crashes
        ▼
  for r in results:
     PowerScheduler.update_frequencies(r.coverage_id)
     if r.new_path: energy = calculate_energy(...) → corpus.add_interesting_input
     if r.error:    corpus.record_crash("ExcType: msg", severity)   # → crashes.json
        │
        ▼  after all targets:
  raw     = corpus.get_crashes()
  deduped = CrashDeduplicator.deduplicate(raw)     # collapse by normalized error signature
  corpus.write_deduplicated_crashes(deduped)       # rewrite crashes.json deduped
  PytestExporter.export(deduped, ...)              # synthedge/exporter.py
        └─ per crash: InputMinimizer.minimize → shortest input with same error signature
        └─ writes synthedge_findings.py (valid pytest, nan/inf-safe reprs)
```

## Components

### Discovery — [discovery.py](edge_case_engine/discovery.py)
`TargetDiscovery` scans a module via `inspect.getmembers`, keeps functions carrying
`__fuzz_contract__`, and wraps each in a frozen `FuzzTarget(function, name, module, parameters,
contract)`. No manual registration.

### Contracts — [contracts.py](edge_case_engine/contracts.py)
`@fuzz_contract(allowed_exceptions=(...))` attaches a `FuzzContract` (declares `allowed_exceptions`
and default `crash_exceptions`). Unlike the older revision, the contract is now **enforced** by the
executor.

### Type handlers + registry — [type_handlers/](type_handlers/)
Each handler exposes `generate_edge_cases() -> list` of adversarial values:
`FloatHandler` (±inf, nan, float max/min…), `IntegerHandler` (boundaries, big ints, type confusion),
`StringHandler` (unicode, null byte, injection, long strings), `BoolHandler`, `NoneHandler`.
`HandlerRegistry.handlers_for_params(params, annotations)` maps each parameter's type hint to a
handler (`float/int/str/bool`), **falling back to `FloatHandler`** for unannotated/unknown params.

### Seed generation — [engine.py](edge_case_engine/engine.py) + [combinatorial.py](edge_case_engine/combinatorial.py)
`EdgeCaseEngine.generate(handlers)` = `itertools.product` across each handler's edge cases, plus one
round of `MutationEngine.mutate`, deduped via `set()`. Output: list of input tuples.

### Mutation — [mutation.py](edge_case_engine/mutation.py)
`mutate(cases)` replaces one random position with a value from a fixed pool
(`None, "string", inf, nan, 0, -1, 1e308`), capped at 50. `havoc_mutate(cases, stack_depth)` applies
`stack_depth` sequential mutations (AFL "havoc"); depth comes from seed energy.
> [mutation_engine.py](edge_case_engine/mutation_engine.py) holds a second, **unused** numeric-only
> `MutationEngine` (same class name) — legacy, not imported.

### Execution & coverage — [executor.py](edge_case_engine/executor.py) + [path_tracker.py](edge_case_engine/path_tracker.py)
`FunctionExecutor.execute(fn, cases)` runs `fn(*case)`, times it (`perf_counter`), and asks the
`PathTracker` for a coverage id. **Contract-aware:** an exception whose type is in the function's
`allowed_exceptions` is treated as expected (`error=None`, `INFO`); anything else is a crash (`HIGH`).
`PathTracker` records executed `"file:line"` pairs into a set and sha256-hashes the sorted set.
It uses **`sys.monitoring`** (Python 3.12+, tool id 3) when available and falls back to
**`sys.settrace`**; it filters out stdlib (`sysconfig` prefix), `site-packages`, and itself so the
path id reflects only the target's own lines.

### Scheduling — [scheduler.py](edge_case_engine/scheduler.py)
`PowerScheduler` keeps `global_edge_frequencies`. `calculate_energy(exec_time_ms, coverage_id)` =
`100 * speed_multiplier * (rarity*10)`, floored at 1.0 (favor fast inputs hitting rare paths).
`choose_next_seed` is roulette-wheel by energy; `determine_mutation_stack_depth` returns
`randint(1, min(16, energy//10))`.

### Persistence — [corpus.py](edge_case_engine/corpus.py)
`CorpusManager` dedupes inputs by sha256 (→ `inputs.json`), appends crashes (→ `crashes.json`), and
exposes `get_crashes` / `write_deduplicated_crashes` (rewrites crashes.json with the deduped list).
Interesting inputs (seeds w/ energy) are **in-memory only**. Schemas: [DATABASE.md](DATABASE.md).

### Dedup & minimization — [deduplicator.py](edge_case_engine/deduplicator.py) + [minimizer.py](edge_case_engine/minimizer.py)
`CrashDeduplicator.signature` normalizes an error message (quotes → `'<type>'`, numbers → `<N>`,
addresses → `<addr>`) and keeps one representative per signature (shortest input).
`InputMinimizer.minimize` is delta-debugging-style: it substitutes each tuple element with simple
values (`0, "", None, …`) and keeps any candidate that reproduces the same error signature and is
smaller.

### Pytest export — [exporter.py](synthedge/exporter.py)
`PytestExporter.export(crashes, module_path, function_registry, output_path)` writes a runnable
pytest file. It infers which function produced each crash (by re-running each registered function),
minimizes the input, renders nan/inf-safe `repr`s, sanitizes exception type names and docstrings, and
emits `with pytest.raises(<ExcType>): fn(*input)` tests. Returns the count written.

## Design properties & current limits

- **Deterministic discovery, stochastic search** (`random` is unseeded → non-reproducible runs).
- **No external deps in the core**; `examples/real_world_targets.py` needs `humanize/validators/boltons`.
- **Coverage is line-level**; the `sys.monitoring` path is faster than the legacy `settrace`.
- **Severity is binary** (`INFO`/`HIGH`); there is no graded severity model.
- `main.py` (legacy) does not run dedup/export — only the CLI does.
