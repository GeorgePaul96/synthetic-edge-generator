# Synthedge Findings Report

## Libraries tested

- `humanize` 4.15.0 -- human-readable formatting of numbers, sizes, and dates
- `validators` 0.35.0 -- string validation (email, URL, IPv4, UUID, etc.)
- `boltons` 25.0.0 -- utility belt of Python helpers (strutils, mathutils, etc.)

## Fuzzing run

```
synthedge examples/real_world_targets.py -n 500 -v
```

- **12 target functions** fuzzed across 3 libraries
- **1,193 total crashes** collected
- **4 unique crashes** after deduplication
- **5 real/interesting findings** identified (including two silent wrong-output bugs)

---

## Findings

### Finding 1: [REAL] `humanize.naturalsize` -- crashes on `float("nan")`

**Input:** `float("nan")`
**Exception:** `ValueError: cannot convert float NaN to integer`
**Severity:** HIGH
**Analysis:** `naturalsize` is documented to accept any number representing a byte
count. `float("nan")` is a valid Python float and a plausible result of a
computation (e.g., a sensor that failed), but the function crashes with an unhandled
`ValueError` deep inside its log computation. The sister functions `intword`,
`intcomma`, and `scientific` all handle NaN gracefully (returning `"NaN"`),
making this an inconsistency within the library itself.

**Reproducer:**
```python
import humanize
humanize.naturalsize(float("nan"))  # raises ValueError: cannot convert float NaN to integer
```

---

### Finding 2: [INTERESTING] `humanize.naturalsize` -- silent garbage output for `float("inf")`

**Input:** `float("inf")`
**Output:** `"inf QB"`
**Exception:** *(none -- silent wrong output)*
**Severity:** MEDIUM
**Analysis:** `naturalsize(float("inf"))` silently returns `"inf QB"`, where `QB`
(quettabyte) is the largest SI prefix (10^30). This is nonsensical: infinity is not
10^30 bytes, and the output leaks an internal implementation detail (the last entry
in the suffix list). All other humanize functions return `"+Inf"` for infinity
inputs. Callers relying on the output string will silently display misleading
information.

**Reproducer:**
```python
import humanize
print(humanize.naturalsize(float("inf")))   # prints "inf QB" instead of "+Inf" or raising
print(humanize.naturalsize(float("-inf")))  # prints "-inf QB"
```

---

### Finding 3: [REAL] `boltons.strutils.parse_int_list` -- crashes on negative integers

**Input:** `"-3"` (a string representation of a negative integer)
**Exception:** `ValueError: invalid literal for int() with base 10: ""`
**Severity:** HIGH
**Analysis:** `parse_int_list` parses compact integer-range strings like `"1-3"` or
`"5,7-9"`. It uses `-` as a range delimiter, so `"-3"` is split into `["" , "3"]`
-- yielding an empty string before the hyphen. The function contains no guard for
negative numbers. Critically, the companion `format_int_list` *does* accept negative
integers and emits `"-1-1"` for `[-1, 0, 1]`, but `parse_int_list("-1-1")` then
crashes -- the round-trip is broken for any list containing negative numbers.

**Reproducer:**
```python
from boltons.strutils import parse_int_list, format_int_list

parse_int_list("-3")                       # raises ValueError
parse_int_list(format_int_list([-1, 0]))   # also crashes -- broken round-trip
```

---

### Finding 4: [INTERESTING] `boltons.strutils.bytes2human` -- returns `"infZ"`/`"nanZ"` for non-finite floats

**Input:** `float("inf")`, `float("nan")`
**Output:** `"infZ"`, `"nanZ"`
**Exception:** *(none -- silent wrong output)*
**Severity:** MEDIUM
**Analysis:** `bytes2human` formats a byte count into a human-readable string with an
SI suffix. For `float("inf")` it returns `"infZ"` and for `float("nan")` returns
`"nanZ"`, where `Z` is the zettabyte suffix -- a meaningless concatenation of the
float's string representation with the last-matched suffix character. Neither output
is parseable, human-readable, or correct. The function should either raise `ValueError`
for non-finite inputs or return a sentinel like `"+Inf"`.

**Reproducer:**
```python
from boltons.strutils import bytes2human

print(bytes2human(float("inf")))  # "infZ"  -- wrong
print(bytes2human(float("nan")))  # "nanZ"  -- wrong
```

---

### Finding 5: [REAL] `validators.email` / `validators.uuid` -- inconsistent AttributeError on truthy non-string input

**Input:** any truthy non-string (e.g., `1`, `2.5`, `float("nan")`, `float("inf")`)
**Exception:** `AttributeError: "int" object has no attribute "count"` (email)
             `AttributeError: "int" object has no attribute "replace"` (uuid)
**Severity:** HIGH
**Analysis:** Both functions accept any Python value but crash with `AttributeError`
for truthy non-string inputs. Falsy non-string values (`0`, `None`, `[]`, `False`)
are handled gracefully and return a `ValidationError`. The inconsistency arises because
the library short-circuits on falsy values early but only applies string methods later.
This is a public API bug: users who defensively pass a non-string expecting a
`ValidationError` will get an unhandled `AttributeError` for every truthy non-string
value. The same pattern likely affects `validators.url`, `validators.ipv4`, and
other validators in the library.

**Reproducer:**
```python
import validators

validators.email(0)            # OK -- returns ValidationError(falsy short-circuit)
validators.email(1)            # CRASH -- AttributeError: "int" object has no attribute "count"
validators.email(float("nan")) # CRASH -- AttributeError: "float" object has no attribute "count"

validators.uuid(0)             # OK -- returns ValidationError
validators.uuid(1)             # CRASH -- AttributeError: "int" object has no attribute "replace"
```

---

## Summary

| # | Library | Function | Type | Input | Result |
|---|---------|----------|------|-------|--------|
| 1 | humanize | `naturalsize` | REAL | `float("nan")` | `ValueError` |
| 2 | humanize | `naturalsize` | INTERESTING | `float("inf")` | silent `"inf QB"` |
| 3 | boltons | `parse_int_list` | REAL | `"-3"` | `ValueError` |
| 4 | boltons | `bytes2human` | INTERESTING | `float("inf")` | silent `"infZ"` |
| 5 | validators | `email`, `uuid` | REAL | `1` (truthy non-str) | `AttributeError` |

- **1,193 total crashes** before deduplication
- **4 unique crash signatures** after deduplication by synthedge
- **3 real bugs** (unexpected exceptions on inputs the library should handle)
- **2 interesting silent bugs** (no exception, but nonsensical/misleading output)
- **0 false positives** in the above findings
