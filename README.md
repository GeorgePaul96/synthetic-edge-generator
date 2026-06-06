# synthedge

Automatically find inputs that break your Python functions — no property writing required.

<!-- TODO: add demo GIF here -->

```
synthedge v0.1.0 — fuzzing examples/real_world_targets.py

Deduplication: 1193 crashes → 4 unique

==================================================
SYNTHEDGE RESULTS
==================================================
  fuzz_humanize_naturalsize        500 iters     3 crashes  [CRASHES FOUND]
  fuzz_boltons_parse_int_list      500 iters     1 crashes  [CRASHES FOUND]
  fuzz_validators_email            500 iters     2 crashes  [CRASHES FOUND]
  fuzz_validators_uuid             500 iters     1 crashes  [CRASHES FOUND]
  fuzz_boltons_bytes2human         500 iters     0 crashes  [Clean]
==================================================
  Total real crashes: 7
  See corpus/crashes.json for details.
Pytest file written: examples/synthedge_findings.py (4 test cases)
```

## Why synthedge?

Most bugs come from inputs the developer never thought to test: `float("nan")`,
negative integers where only positive were expected, empty strings, type mismatches.
synthedge generates adversarial edge cases automatically from your type hints, runs
them against your functions, deduplicates the crash signatures, and hands you a
ready-to-run pytest file. It is aimed at Python developers who want to harden
libraries, APIs, or data-processing pipelines without writing property-based tests.

## Real findings

Fuzzed against `humanize 4.15.0`, `boltons 25.0.0`, and `validators 0.35.0`:

- `humanize.naturalsize(float("nan"))` raises `ValueError: cannot convert float NaN
  to integer`. The sister functions `intword`, `intcomma`, and `scientific` all return
  `"NaN"` gracefully — this is an inconsistency within the library.
- `boltons.strutils.parse_int_list("-3")` raises `ValueError` because `-` is used as
  a range delimiter. `format_int_list([-1, 0])` emits `"-1-0"`, which `parse_int_list`
  then crashes on — the round-trip is broken for any list containing negative numbers.
- `validators.email(1)` and `validators.uuid(1)` raise `AttributeError` on any truthy
  non-string input. Falsy non-strings (`0`, `None`) are handled gracefully. The
  inconsistency means defensive callers get unexpected crashes instead of
  `ValidationError`.

## Install

```bash
pip install synthedge
# or for local development:
pip install -e .
```

## Quick start

**1. Decorate your function:**

```python
from edge_case_engine.contracts import fuzz_contract

@fuzz_contract(allowed_exceptions=(TypeError,))
def parse_size(value: float) -> str:
    return some_library.format_bytes(value)
```

**2. Run synthedge:**

```bash
synthedge targets.py -n 500 -v
```

**3. Read the output:**

```
synthedge v0.1.0 — fuzzing targets.py

Deduplication: 23 crashes → 2 unique

==================================================
SYNTHEDGE RESULTS
==================================================
  parse_size                        500 iters     2 crashes  [CRASHES FOUND]
==================================================
  Total real crashes: 2
  See corpus/crashes.json for details.
Pytest file written: synthedge_findings.py (2 test cases)
```

## How it works

synthedge discovers every `@fuzz_contract` function in your module, generates
adversarial inputs from the type hints (including boundary values, non-finite floats,
empty strings, and mixed types), executes them while tracking unique code paths, deduplicates
crash signatures down to minimal representative inputs, and exports a `synthedge_findings.py`
pytest file you can drop straight into your test suite.

## Writing fuzz targets

`allowed_exceptions` lists exception types that are acceptable contract behavior.
Any other exception is recorded as a crash.

```python
from edge_case_engine.contracts import fuzz_contract

# Only TypeError is acceptable — anything else is a bug.
@fuzz_contract(allowed_exceptions=(TypeError,))
def process(value: float, label: str) -> str:
    ...

# No exceptions allowed at all — every raise is a crash.
@fuzz_contract(allowed_exceptions=())
def validate(email: str) -> bool:
    ...
```

Type hints drive input generation. `float` produces boundary values including `nan`,
`inf`, `-inf`, `0.0`, and very large numbers. `str` produces empty strings, unicode,
whitespace, control characters, and numeric-looking strings. Mixed-type signatures
get all combinations.

## Output

**`corpus/crashes.json`** — deduplicated crash records:

```json
[
  {
    "input": [["NaN"]],
    "error": "ValueError: cannot convert float NaN to integer",
    "severity": "HIGH"
  }
]
```

**`synthedge_findings.py`** — drop-in pytest file:

```python
import pytest
from targets import parse_size

def test_parse_size_crash_0():
    with pytest.raises(Exception):
        parse_size(float('nan'))
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `-n`, `--iterations` | `300` | Fuzzing iterations per target |
| `-v`, `--verbose` | off | Print new code paths as they are discovered |

## Positioning

synthedge is not Hypothesis — it generates adversarial inputs automatically without
requiring you to write properties or strategies.

## License

MIT
