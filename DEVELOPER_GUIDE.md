# DEVELOPER_GUIDE.md

Practical guide for changing **synthedge** — for humans and Claude Code sessions. Pairs with
[ARCHITECTURE.md](ARCHITECTURE.md) and [API_MAP.md](API_MAP.md).

## Setup & run

```bash
python --version            # 3.9+ (3.12+ enables the fast sys.monitoring coverage path)
pip install -e .            # installs the `synthedge` console command
pip install pytest          # for the test suite (not a runtime dep)

synthedge operations.py -n 300 -v        # fuzz the demo targets via the CLI
python main.py                           # legacy harness (fuzzes operations.py, no dedup/export)
python -m pytest                         # run tests
```

`examples/real_world_targets.py` also needs `pip install humanize validators boltons`.

> Note: in the environment this guide was generated, the active interpreter was Python 3.8.8 without
> pytest, so the suite was not executed here. On 3.9+ with pytest installed it is the standard runner.

## Common tasks (and exactly which files to touch)

### Add a function to fuzz
1. Write the function in [operations.py](operations.py) (or any module you pass to the CLI).
2. Decorate: `@fuzz_contract(allowed_exceptions=(ValueError,))` — list the exceptions that are
   acceptable behavior; everything else is reported as a crash.
3. Run `synthedge <file.py>`. Auto-discovered, no registration.
- Files: the target module only.

### Add a new input type/domain
1. Create `type_handlers/<name>_handler.py` with a class exposing `generate_edge_cases() -> list`.
2. Register it in [type_handlers/registry.py](type_handlers/registry.py) `_TYPE_MAP` (`<pytype>: <Handler>`).
- Files: new handler + `registry.py`. (The CLI picks handlers by type hint automatically.)

### Change mutation behavior
- Edit [mutation.py](edge_case_engine/mutation.py) (`mutate`, `havoc_mutate`). The live one.
- Ignore [mutation_engine.py](edge_case_engine/mutation_engine.py) (unused; shares the class name).

### Change search strategy / energy
- Edit [scheduler.py](edge_case_engine/scheduler.py) and the loop in
  [synthedge/cli.py](synthedge/cli.py) (`run_fuzzer`). `main.py` has a parallel legacy loop — usually
  leave it alone.

### Change crash classification / severity
- Edit [executor.py](edge_case_engine/executor.py). It reads `func.__fuzz_contract__`;
  `allowed_exceptions` are not crashes. Severity is binary (`INFO`/`HIGH`).

### Change dedup / minimization / exported tests
- Dedup signatures: [deduplicator.py](edge_case_engine/deduplicator.py).
- Input shrinking: [minimizer.py](edge_case_engine/minimizer.py).
- Generated pytest format: [exporter.py](synthedge/exporter.py).

## Focused-context workflow (keep Claude cheap)

Start from the docs, not a scan:

| Task | Read first | Then likely edit |
|---|---|---|
| **Bug fix** | failing file via [PROJECT_MAP.md](PROJECT_MAP.md) + [API_MAP.md](API_MAP.md) | that one file |
| **New target** | this guide → "Add a function" | `operations.py` / your module |
| **New input type** | this guide → "Add a new input type" | `type_handlers/`, `registry.py` |
| **Mutation/search** | [ARCHITECTURE.md](ARCHITECTURE.md) §Mutation/Scheduling | `mutation.py` / `scheduler.py` / `cli.py` |
| **Export/dedup/minimize** | [ARCHITECTURE.md](ARCHITECTURE.md) §Dedup & §Export | `exporter.py` / `deduplicator.py` / `minimizer.py` |
| **Coverage/perf** | [ARCHITECTURE.md](ARCHITECTURE.md) §Execution & coverage | `path_tracker.py` |
| **Security/contract audit** | [ARCHITECTURE.md](ARCHITECTURE.md) §Contracts + `executor.py` | `executor.py`, `contracts.py` |
| **Architecture review** | [ARCHITECTURE.md](ARCHITECTURE.md) only | — |

Rules of thumb for agents:
- **Never** open `corpus/*.json`, `synthedge_findings.py`, `examples/corpus/*.json`,
  `**/__pycache__/**`, or `docs/*.md` to understand code. Use [DATABASE.md](DATABASE.md) for schemas.
- The active engine+product is 22 files / ~1,560 LOC — name the file from
  [PROJECT_MAP.md](PROJECT_MAP.md) and open it directly instead of grepping the repo.
- The **CLI** (`synthedge/cli.py`) is authoritative; `main.py` is legacy. Verify which path a change
  affects before editing.

## Testing

`tests/` holds 6 pytest modules (~1,070 LOC) covering CLI, contract filtering, dedup, exporter,
handler registry, and path tracker. Run with `python -m pytest`. New tests go in `tests/`.

## Known issues / cleanup backlog (not auto-changed — confirm intent)

1. **Dead module:** [mutation_engine.py](edge_case_engine/mutation_engine.py) is unused and collides
   on the name `MutationEngine`. Candidate for deletion or merge into `mutation.py`.
2. **Unused demo:** [examples/example_functions.py](examples/example_functions.py) has no contracts
   and is never imported.
3. **Two run paths:** `main.py` (legacy) duplicates the CLI's loop without dedup/export. Consider
   making `main.py` delegate to `synthedge.cli.run_fuzzer`, or removing it.
4. **Unseeded randomness:** mutation/selection use `random` without a seed → non-reproducible runs.
   Consider a `--seed` flag for deterministic repros.

## History note

The latest code formerly lived on an unmerged git worktree branch (`worktree-mvp-d1-d14`) under
`.claude/worktrees/`. It has been fast-forwarded into `main`; that branch now equals `main` and the
worktree was removed. There should be no second copy of the project to confuse you.
