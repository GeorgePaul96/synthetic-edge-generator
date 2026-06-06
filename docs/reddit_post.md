**Title:** I built a tool that automatically finds edge case bugs in Python libraries – found 3 real bugs in popular packages

**Body:**

I got frustrated writing the same boundary-value tests over and over — `float("nan")`, empty strings, `None` where a string was expected — so I built a tool that generates those inputs automatically from type hints and runs them against your functions.

To check it actually works, I fuzzed three popular libraries before posting. Found some genuinely interesting bugs:

- `humanize.naturalsize(float("nan"))` crashes with `ValueError`. The other humanize number functions handle NaN fine.
- `boltons.strutils.parse_int_list("-3")` crashes because `-` is the range delimiter. Even better: `format_int_list([-1, 0])` emits `"-1-0"`, which then crashes `parse_int_list` — the round-trip is broken for negative numbers.
- `validators.email(1)` and `validators.uuid(1)` raise `AttributeError`. Pass `0` or `None` and you get a proper `ValidationError`. Pass any truthy non-string and it crashes. Classic falsy short-circuit bug.

Usage looks like this:

```python
# targets.py
from edge_case_engine.contracts import fuzz_contract
import humanize

@fuzz_contract(allowed_exceptions=(TypeError,))
def fuzz_naturalsize(value: float) -> str:
    return humanize.naturalsize(value)
```

```bash
$ synthedge targets.py -n 500

synthedge v0.1.0 — fuzzing targets.py

Deduplication: 47 crashes → 1 unique

==================================================
SYNTHEDGE RESULTS
==================================================
  fuzz_naturalsize               500 iters     1 crashes  [CRASHES FOUND]
==================================================
  Total real crashes: 1
  See corpus/crashes.json for details.
Pytest file written: synthedge_findings.py (1 test cases)
```

It writes a pytest file with the minimal reproducing input, so you can commit the finding directly as a regression test.

The approach is coverage-guided (uses `sys.monitoring` for path tracking) and deduplicates by error type + traceback hash, so you get 1 actionable crash instead of 500 copies of the same one.

Main limitation: it is good at boundary values and type confusion, not great at bugs that need semantically structured inputs. It also requires a thin `@fuzz_contract` wrapper around third-party functions.

GitHub: https://github.com/[your-repo]

Would love feedback on whether the decorator-based API is the right approach, or whether there's a better way to let people point it at existing code without writing wrappers.
