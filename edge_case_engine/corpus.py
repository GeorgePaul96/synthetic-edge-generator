"""
corpus.py

Persistent corpus management for fuzzing engine.

Responsibilities:
• Deduplicate test inputs
• Persist corpus across runs
• Store crashes separately
• Enable replay of crashing inputs
• Remain scalable and storage-agnostic
"""

import json
import os
import hashlib
from typing import Any, List, Tuple


class CorpusManager:

    def __init__(self, corpus_dir: str = "corpus"):
        self.corpus_dir = corpus_dir
        self.inputs_file = os.path.join(corpus_dir, "inputs.json")
        self.crashes_file = os.path.join(corpus_dir, "crashes.json")

        os.makedirs(self.corpus_dir, exist_ok=True)

        self._seen_hashes = set()
        self._load_existing_inputs()

    # -------------------------
    # Internal Utilities
    # -------------------------

    def _hash_input(self, test_input: Tuple[Any, ...]) -> str:
        """
        Create deterministic hash of input tuple.
        Handles non-serializable objects safely.
        """
        serialized = json.dumps(
            test_input,
            default=str,
            sort_keys=True
        )
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _load_existing_inputs(self):
        if not os.path.exists(self.inputs_file):
            return

        with open(self.inputs_file, "r") as f:
            data = json.load(f)

        for item in data:
            h = self._hash_input(tuple(item))
            self._seen_hashes.add(h)

    def _append_json(self, filepath: str, data):
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

    def add_inputs(self, test_cases: List[Tuple[Any, ...]]) -> List[Tuple[Any, ...]]:
        """
        Deduplicate and persist new test cases.

        Returns:
            List of new unique test cases.
        """
        new_cases = []

        for case in test_cases:
            h = self._hash_input(case)

            if h in self._seen_hashes:
                continue

            self._seen_hashes.add(h)
            new_cases.append(case)

            self._append_json(self.inputs_file, case)

        return new_cases

    def record_crash(self, test_input: Tuple[Any, ...], error: str, severity: str):
        """
        Persist crash details.
        """
        crash_record = {
            "input": test_input,
            "error": error,
            "severity": severity,
        }

        self._append_json(self.crashes_file, crash_record)

    def load_crashes(self):
        if not os.path.exists(self.crashes_file):
            return []

        with open(self.crashes_file, "r") as f:
            return json.load(f)