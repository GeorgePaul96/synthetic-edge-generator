# CLAUDE.md — synthedge

> Entry point for any Claude Code session in this repo. Read this first.
> Deeper detail: [ARCHITECTURE.md](ARCHITECTURE.md) · [PROJECT_MAP.md](PROJECT_MAP.md) ·
> [API_MAP.md](API_MAP.md) · [DATABASE.md](DATABASE.md) · [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).
> User-facing intro is [README.md](README.md).

## What this is

**synthedge** (`v0.1.0`) — a coverage-guided fuzzer for Python functions. You decorate functions
with `@fuzz_contract`, point synthedge at the file, and it generates adversarial inputs from the
type hints, runs them while tracing code coverage, deduplicates crashes down to minimal inputs, and
**writes a ready-to-run pytest file** (`synthedge_findings.py`).

- **Language:** Python (packaging targets **3.9+**; uses `sys.monitoring` fast path on **3.12+**,
  falls back to `sys.settrace` below that).
- **Dependencies:** standard library only for the core. Packaging via `setuptools` (see
  [pyproject.toml](pyproject.toml)). `examples/real_world_targets.py` additionally needs `humanize`,
  `validators`, `boltons` installed.
- **Distribution:** installable package exposing the `synthedge` console command
  (`[project.scripts] synthedge = "synthedge.cli:main"`).

## Two ways it runs (don't confuse them)

| Path | Command | Target | Role |
|---|---|---|---|
| **Product CLI** | `synthedge <file.py> -n 500 -v` → [synthedge/cli.py](synthedge/cli.py) | any module you pass | The real tool: discovery → fuzz → dedup → **pytest export** |
| **Legacy harness** | `python main.py` → [main.py](main.py) | hardcoded `operations` | Older demo loop; no dedup/export. Kept but superseded by the CLI |

When in doubt, the **CLI** (`synthedge/cli.py:run_fuzzer`) is the source of truth for behavior.

## 30-second mental model (CLI path)

```
synthedge <module>            synthedge/cli.py:run_fuzzer
  ├─ load module + TargetDiscovery   → @fuzz_contract functions
  ├─ HandlerRegistry.handlers_for_params(types) → input generators
  ├─ EdgeCaseEngine.generate         → seed inputs (combinatorial + mutation)
  ├─ evolutionary loop (-n iters):
  │     PowerScheduler.choose_next_seed → havoc_mutate → FunctionExecutor.execute
  │     → PathTracker coverage → new path? keep : crash? record (contract-aware)
  ├─ CrashDeduplicator.deduplicate   → collapse to unique signatures
  └─ PytestExporter.export           → synthedge_findings.py (+ InputMinimizer)
```

## Where things live (active source — 22 `.py`, ~1,560 LOC excl. tests)

| Concern | File |
|---|---|
| **Product CLI / orchestration** | [synthedge/cli.py](synthedge/cli.py) |
| **Pytest export + input minimization use** | [synthedge/exporter.py](synthedge/exporter.py) |
| Seed generation | [edge_case_engine/engine.py](edge_case_engine/engine.py) + [combinatorial.py](edge_case_engine/combinatorial.py) |
| Mutation (single + havoc) — **in use** | [edge_case_engine/mutation.py](edge_case_engine/mutation.py) |
| Target discovery / `FuzzTarget` | [edge_case_engine/discovery.py](edge_case_engine/discovery.py) |
| `@fuzz_contract` decorator | [edge_case_engine/contracts.py](edge_case_engine/contracts.py) |
| Execution + timing (**contract-aware**) | [edge_case_engine/executor.py](edge_case_engine/executor.py) |
| Coverage path id (`sys.monitoring`/`settrace`) | [edge_case_engine/path_tracker.py](edge_case_engine/path_tracker.py) |
| Energy / roulette / havoc depth | [edge_case_engine/scheduler.py](edge_case_engine/scheduler.py) |
| Corpus persistence + dedup write | [edge_case_engine/corpus.py](edge_case_engine/corpus.py) |
| Crash dedup (error-signature) | [edge_case_engine/deduplicator.py](edge_case_engine/deduplicator.py) |
| Input minimization (delta-debugging) | [edge_case_engine/minimizer.py](edge_case_engine/minimizer.py) |
| Type hint → handler map | [type_handlers/registry.py](type_handlers/registry.py) |
| Input generators | [type_handlers/](type_handlers/) (`float/integer/string/bool/none`) |
| Demo targets | [operations.py](operations.py), [examples/real_world_targets.py](examples/real_world_targets.py) |
| Tests | [tests/](tests/) (6 files, ~1,070 LOC) |
| Output (generated) | `corpus/*.json`, `synthedge_findings.py` — see [DATABASE.md](DATABASE.md) |

## Gotchas (verify before trusting)

- **Two classes named `MutationEngine`.** [mutation.py](edge_case_engine/mutation.py) is wired in.
  [mutation_engine.py](edge_case_engine/mutation_engine.py) is a separate numeric variant **not
  imported anywhere** — dead/legacy.
- **`examples/example_functions.py`** has no `@fuzz_contract` and is unused (legacy demo).
- **`corpus/*.json` and `synthedge_findings.py` are generated**, now git-ignored. Don't read them to
  understand code — schemas are in [DATABASE.md](DATABASE.md). `examples/corpus/*.json` is a small
  committed showcase the README cites.
- **`main.py` ≠ the product.** It is the legacy harness; the CLI is the real path.
- This repo's latest code previously lived on an unmerged worktree branch; it has now been merged
  into `main`. There should be **no `.claude/worktrees/` copy** to read.

## Running

```bash
pip install -e .                         # install the synthedge command
synthedge operations.py -n 300 -v        # fuzz the demo targets
python -m pytest                         # run the test suite (needs pytest, Python 3.9+)
```

## Conventions

- Core stays pure-stdlib. Targets opt in via `@fuzz_contract(allowed_exceptions=(...))`.
- New input domains = a handler class in [type_handlers/](type_handlers/) exposing
  `generate_edge_cases()`, registered in [registry.py](type_handlers/registry.py).
