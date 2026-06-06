"""
Tests for PytestExporter.

These tests use unittest only — pytest is NOT required to run them.
The generated pytest files themselves use `import pytest`, which is
intentional (they are run by users who have pytest installed).
"""

import os
import sys
import tempfile
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from synthedge.exporter import PytestExporter


def _type_error_func(a, b):
    """Raises TypeError when a is None."""
    if a is None:
        raise TypeError("a must not be None")
    return a + b


def _value_error_func(x):
    """Raises ValueError when x is negative."""
    if x < 0:
        raise ValueError("x must be non-negative")
    return x


_REGISTRY = {
    "_type_error_func": _type_error_func,
    "_value_error_func": _value_error_func,
}

_ONE_TYPE_CRASH = [
    {
        "input": [None, 1],
        "error": "TypeError: a must not be None",
        "severity": "medium",
    }
]

_ONE_VALUE_CRASH = [
    {
        "input": [-1],
        "error": "ValueError: x must be non-negative",
        "severity": "low",
    }
]

_TWO_CRASHES = _ONE_TYPE_CRASH + _ONE_VALUE_CRASH


class TestPytestExporterEmptyInput(unittest.TestCase):

    def test_empty_crashes_returns_zero(self):
        """export() with no crashes must return 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "out.py")
            result = PytestExporter.export([], "operations.py", {}, out)
            self.assertEqual(result, 0)

    def test_empty_crashes_does_not_create_file(self):
        """export() with no crashes must NOT create the output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "out.py")
            PytestExporter.export([], "operations.py", {}, out)
            self.assertFalse(
                os.path.exists(out),
                "File should not be created when crashes list is empty",
            )


class TestPytestExporterOneCrash(unittest.TestCase):

    def _export_one(self, tmpdir):
        """Helper: export one TypeError crash, return (path, source)."""
        out = os.path.join(tmpdir, "findings.py")
        n = PytestExporter.export(_ONE_TYPE_CRASH, "operations.py", _REGISTRY, out)
        with open(out) as f:
            source = f.read()
        return out, source, n

    def test_one_crash_returns_one(self):
        """export() with one crash must return 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, _, n = self._export_one(tmpdir)
            self.assertEqual(n, 1)

    def test_one_crash_file_contains_import_pytest(self):
        """Generated file must contain 'import pytest'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, source, _ = self._export_one(tmpdir)
            self.assertIn("import pytest", source)

    def test_one_crash_file_contains_test_function(self):
        """Generated file must contain a 'def test_synthedge_' function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, source, _ = self._export_one(tmpdir)
            self.assertIn("def test_synthedge_", source)

    def test_one_type_error_crash_contains_pytest_raises_typeerror(self):
        """TypeError crash must produce 'pytest.raises(TypeError)' in the file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, source, _ = self._export_one(tmpdir)
            self.assertIn("pytest.raises(TypeError)", source)

    def test_generated_file_is_valid_python(self):
        """The generated file must be parseable by compile()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out, source, _ = self._export_one(tmpdir)
            try:
                compile(source, out, "exec")
            except SyntaxError as e:
                self.fail(f"Generated file has a SyntaxError: {e}\n\nSource:\n{source}")


class TestPytestExporterMultipleCrashes(unittest.TestCase):

    def test_n_crashes_produces_n_test_functions(self):
        """Exporting N crashes must produce exactly N 'def test_synthedge_' lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "findings.py")
            n = PytestExporter.export(_TWO_CRASHES, "operations.py", _REGISTRY, out)
            with open(out) as f:
                source = f.read()
            count = source.count("def test_synthedge_")
            self.assertEqual(count, n)
            self.assertEqual(n, 2)

    def test_n_crashes_returns_n(self):
        """export() must return the count equal to the number of crashes supplied."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "findings.py")
            n = PytestExporter.export(_TWO_CRASHES, "operations.py", _REGISTRY, out)
            self.assertEqual(n, len(_TWO_CRASHES))

    def test_multiple_crashes_file_is_valid_python(self):
        """File produced from multiple crashes must be valid Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "findings.py")
            PytestExporter.export(_TWO_CRASHES, "operations.py", _REGISTRY, out)
            with open(out) as f:
                source = f.read()
            try:
                compile(source, out, "exec")
            except SyntaxError as e:
                self.fail(f"Generated file has a SyntaxError: {e}\n\nSource:\n{source}")

    def test_value_error_crash_contains_pytest_raises_valueerror(self):
        """A ValueError crash must also produce 'pytest.raises(ValueError)'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "findings.py")
            PytestExporter.export(_TWO_CRASHES, "operations.py", _REGISTRY, out)
            with open(out) as f:
                source = f.read()
            self.assertIn("pytest.raises(ValueError)", source)


class TestPytestExporterFunctionNames(unittest.TestCase):

    def test_test_names_are_valid_identifiers(self):
        """Every generated test function name must be a valid Python identifier."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "findings.py")
            PytestExporter.export(_TWO_CRASHES, "operations.py", _REGISTRY, out)
            with open(out) as f:
                source = f.read()
            for line in source.splitlines():
                line = line.strip()
                if line.startswith("def test_synthedge_"):
                    # Extract the function name (strip "def " and "()" and ":")
                    name = line[4:].split("(")[0]
                    self.assertTrue(
                        name.isidentifier(),
                        f"Generated function name is not a valid identifier: {name!r}",
                    )


if __name__ == "__main__":
    unittest.main()
