**Title:** Show HN: synthedge – auto-find inputs that break Python functions (found bugs in humanize, boltons, validators)

**Body:**

I built a coverage-guided fuzzer for Python functions that generates adversarial edge cases from type hints. Before posting, I ran it against three popular libraries to verify it finds real bugs. It did.

**What it found:**

`humanize.naturalsize(float("nan"))` crashes with `ValueError: cannot convert float NaN to integer`. The sister functions `intword`, `intcomma`, and `scientific` all return `"NaN"` gracefully — this is an inconsistency within the library's own API surface.

`boltons.strutils.parse_int_list("-3")` crashes with `ValueError: invalid literal for int() with base 10: ""`. The `-` character is the range delimiter, so `"-3"` splits into `["", "3"]`. Worse: `format_int_list([-1, 0])` emits `"-1-0"`, which `parse_int_list` then crashes on — the round-trip is broken for any list containing negative numbers.

`validators.email(1)` and `validators.uuid(1)` raise `AttributeError: 'int' object has no attribute 'count'`. Falsy non-strings (`0`, `None`) are handled gracefully with a `ValidationError`. Truthy non-strings crash unconditionally. The library short-circuits on falsiness before reaching the string methods, so the bug only surfaces on truthy inputs.

1,193 raw crashes reduced to 4 unique signatures after deduplication.

**How it works:**

You decorate a function with `@fuzz_contract(allowed_exceptions=(TypeError,))`, then run `synthedge targets.py -n 500`. synthedge reads the type hints, generates boundary inputs (`nan`, `inf`, `-inf`, `0`, empty string, unicode, control chars, mixed types), and executes them while tracking unique code paths via `sys.monitoring`. Crashes are deduplicated by error type + traceback hash, minimized to the shortest reproducing input, and exported as a `synthedge_findings.py` pytest file you can drop into your test suite.

It is not Hypothesis. You do not write properties or strategies. The tradeoff is that it can only check "this should not crash with an unexpected exception" — it cannot verify semantic correctness unless you encode that in your `allowed_exceptions` contract.

**Limitations:**

- Input space coverage is shallow: it is good at boundary values and type confusion, less good at finding bugs that require semantically structured inputs (e.g., valid JWT tokens with malformed payloads).
- `sys.monitoring` path tracking is Python 3.12+. On 3.9–3.11, path diversity tracking falls back to a simpler execution count.
- No async support yet.
- The `@fuzz_contract` decorator means you need to write thin wrapper functions around third-party code — you cannot fuzz a library function directly without a one-line shim.

**Code:** https://github.com/[your-repo]

Curious whether people find this useful for hardening libraries or pipelines, and whether the contract-based approach is the right abstraction or whether something simpler would work better.
