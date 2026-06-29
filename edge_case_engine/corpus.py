import json
import os
import hashlib
import random

from edge_case_engine.codec import encode, decode, values_equal
from edge_case_engine.recipe import Recipe, materialize


class CorpusIntegrityError(Exception):
    """Raised when a stored recipe does not replay to its cached input."""


class CorpusManager:

    def __init__(self, corpus_dir="corpus", root=None):

        self.corpus_dir = corpus_dir
        self.inputs_file = os.path.join(corpus_dir, "inputs.json")
        self.crashes_file = os.path.join(corpus_dir, "crashes.json")

        os.makedirs(self.corpus_dir, exist_ok=True)

        self._seen_hashes = set()
        self.interesting_inputs = []

        self._load_existing_inputs()

        # ---- v2 envelope store (.synthedge/) ----
        self.root = root or ".synthedge"
        self._interesting_path = os.path.join(self.root, "corpus", "interesting.jsonl")
        self._crashes_path = os.path.join(self.root, "crashes", "crashes.jsonl")
        os.makedirs(os.path.dirname(self._interesting_path), exist_ok=True)
        os.makedirs(os.path.dirname(self._crashes_path), exist_ok=True)

    # -------------------------
    # Internal
    # -------------------------

    def _hash_input(self, test_input):

        serialized = json.dumps(test_input, default=str, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _load_existing_inputs(self):

        if not os.path.exists(self.inputs_file):
            return

        with open(self.inputs_file, "r") as f:
            data = json.load(f)

        for item in data:
            h = self._hash_input(item)
            self._seen_hashes.add(h)

    def _append_json(self, filepath, data):

        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                existing = json.load(f)
        else:
            existing = []

        existing.append(data)

        with open(filepath, "w") as f:
            json.dump(existing, f, indent=2, default=str)

    # -------------------------
    # Public API
    # -------------------------

    def add_inputs(self, test_cases):

        new_cases = []

        for case in test_cases:

            h = self._hash_input(case)

            if h in self._seen_hashes:
                continue

            self._seen_hashes.add(h)
            new_cases.append(case)

            self._append_json(self.inputs_file, case)

        return new_cases

    def add_interesting_input(self, test_input, coverage_id, energy=1.0, exec_time_ms=0.0):

        entry = {
            "input": test_input,
            "coverage_id": coverage_id,
            "energy": energy,
            "exec_time_ms": exec_time_ms
        }
    
        self.interesting_inputs.append(entry)

    def get_all_interesting_inputs(self):
        return self.interesting_inputs
    
    def record_crash(self, test_input, error, severity):

        crash_record = {
            "input": test_input,
            "error": error,
            "severity": severity
        }

        self._append_json(self.crashes_file, crash_record)

    def get_crashes(self) -> list:
        """Return all recorded crashes from disk."""
        if not os.path.exists(self.crashes_file):
            return []
        with open(self.crashes_file, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []

    def write_deduplicated_crashes(self, crashes: list) -> None:
        """Overwrite crashes.json with the given (deduplicated) list."""
        with open(self.crashes_file, "w") as f:
            json.dump(crashes, f, indent=2, default=str)

    # -------------------------
    # v2 envelope API (recipe-based, integrity-checked)
    # -------------------------

    def make_envelope(self, recipe: Recipe, input_value, artifacts=None) -> dict:
        return {
            "version": 1,
            "seed": recipe.seed,
            "recipe": recipe.to_dict(),
            "input": encode(input_value),
            "artifacts": artifacts or {"output": None, "exception": None, "coverage": None},
        }

    def _append_jsonl(self, path, env):
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(env) + "\n")

    def save_interesting(self, env):
        self._append_jsonl(self._interesting_path, env)

    def save_crash(self, env):
        self._append_jsonl(self._crashes_path, env)

    def load_interesting(self):
        return self._load_checked(self._interesting_path)

    def load_crashes_v2(self):
        return self._load_checked(self._crashes_path)

    def _load_checked(self, path):
        if not os.path.exists(path):
            return []
        out = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                env = json.loads(line)
                recipe = Recipe.from_dict(env["recipe"])
                replayed = materialize(recipe)
                cached = decode(env["input"])
                if not values_equal(replayed, cached):
                    raise CorpusIntegrityError(
                        f"recipe replay != cached input (seed={recipe.seed})"
                    )
                out.append(env)
        return out
