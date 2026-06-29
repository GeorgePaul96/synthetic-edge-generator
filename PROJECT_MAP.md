# PROJECT_MAP.md

File inventory + reading guidance for Claude Code. Goal: know what to open and what to skip
**without scanning the tree**. Counts are source `.py` only (bytecode/data excluded).

## Active source tree (read these)

```
synthetic-edge-generator/
├── pyproject.toml              # Packaging; `synthedge` console entry point
├── README.md                   # User-facing intro + real findings
├── CHANGELOG.md                # Release notes
├── main.py                     # LEGACY harness — fuzzes operations.py (no dedup/export)   (92)
├── operations.py               # Demo @fuzz_contract targets (divide/add/multiply/format_ratio) (61)
│
├── synthedge/                  # THE PRODUCT (installable package)
│   ├── cli.py                  # CLI + run_fuzzer — full pipeline (authoritative)          (184)
│   ├── exporter.py             # PytestExporter — writes synthedge_findings.py             (165)
│   └── __init__.py             #                                                            (0)
│
├── edge_case_engine/           # Fuzzing engine
│   ├── engine.py               # EdgeCaseEngine — seed generation orchestrator              (29)
│   ├── combinatorial.py        # CombinatorialGenerator — itertools.product                 (9)
│   ├── mutation.py             # MutationEngine — mutate + havoc_mutate (USED)              (69)
│   ├── mutation_engine.py      # MutationEngine — numeric variant (UNUSED / legacy)         (62)
│   ├── discovery.py            # TargetDiscovery + FuzzTarget                               (95)
│   ├── contracts.py            # @fuzz_contract + FuzzContract                              (20)
│   ├── executor.py             # FunctionExecutor (contract-aware) + ExecutionResult        (56)
│   ├── path_tracker.py         # PathTracker — sys.monitoring/settrace line coverage        (118)
│   ├── scheduler.py            # PowerScheduler — energy/roulette/havoc depth                (58)
│   ├── corpus.py               # CorpusManager — dedupe + JSON persistence                  (115)
│   ├── deduplicator.py         # CrashDeduplicator — error-signature dedup                   (46)
│   └── minimizer.py            # InputMinimizer — delta-debugging shrink                     (62)
│
├── type_handlers/              # Input generators
│   ├── registry.py             # HandlerRegistry — type hint → handler                      (32)
│   ├── float_handler.py        # FloatHandler (USED)                                        (15)
│   ├── integer_handler.py      # IntegerHandler (USED)                                      (61)
│   ├── string_handler.py       # StringHandler (USED)                                       (47)
│   ├── bool_handler.py         # BoolHandler (USED)                                          (3)
│   └── none_handler.py         # NoneHandler (USED)                                          (3)
│
├── examples/
│   ├── real_world_targets.py   # humanize/validators/boltons targets (needs those libs)     (96)
│   ├── example_functions.py    # old demo, no contracts (UNUSED)                             (8)
│   ├── findings_report.md      # write-up of real findings
│   └── corpus/                 # committed SHOWCASE data the README cites (keep)
│
├── tests/                      # pytest suite (~1,070 LOC, 6 files)
│   ├── test_cli.py · test_contract_filtering.py · test_dedup.py
│   └── test_exporter.py · test_handler_registry.py · test_path_tracker.py
│
├── docs/                       # launch marketing (show_hn / reddit_post / launch_checklist) — NON-technical
└── corpus/                     # GENERATED runtime output (git-ignored) — do not read for code
    ├── inputs.json · crashes.json
```

Active engine + product source: **22 `.py`, ~1,560 LOC** (tests add ~1,070). Small enough to open
the specific file rather than grep the whole repo.

## Do NOT read (scanning traps / non-source)

| Path | Why skip |
|---|---|
| `corpus/*.json`, `examples/corpus/*.json`, `synthedge_findings.py` | Generated/data. Schemas in [DATABASE.md](DATABASE.md). (examples/corpus is a small committed showcase — read DATABASE.md, not the JSON.) |
| `**/__pycache__/**`, `*.pyc` | Compiled bytecode (now git-ignored). |
| `docs/*.md` | Launch copy (Show HN / Reddit), not architecture. |
| `.claude/`, `.vscode/`, `.git/` | Tooling/editor/VCS internals. |
| `edge_case_engine/mutation_engine.py`, `examples/example_functions.py` | Unused/legacy — don't model behavior on them. |

## Read order for a new session

1. [CLAUDE.md](CLAUDE.md) — orientation, two run paths, gotchas.
2. [ARCHITECTURE.md](ARCHITECTURE.md) — the pipeline.
3. [API_MAP.md](API_MAP.md) — signatures (when editing).
4. The one relevant source file from the table above.

## Status legend

- **USED** — on the live CLI (`synthedge/cli.py`) path.
- **LEGACY / UNUSED** — present but not on the product path. Confirm intent before extending/deleting.
- **GENERATED** — produced at runtime; never hand-edit, never read to understand behavior.
- **SHOWCASE** — committed example output kept on purpose (`examples/corpus/`).
