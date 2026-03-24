import json
import os
import hashlib
import random


class CorpusManager:

    def __init__(self, corpus_dir="corpus"):

        self.corpus_dir = corpus_dir
        self.inputs_file = os.path.join(corpus_dir, "inputs.json")
        self.crashes_file = os.path.join(corpus_dir, "crashes.json")

        os.makedirs(self.corpus_dir, exist_ok=True)

        self._seen_hashes = set()
        self.interesting_inputs = []

        self._load_existing_inputs()

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

    def add_interesting_input(self, test_input, coverage_id):

        entry = {
            "input": test_input,
            "coverage_id": coverage_id
        }

        self.interesting_inputs.append(entry)

    def get_interesting_input(self):

        if self.interesting_inputs:
            return random.choice(self.interesting_inputs)["input"]

        return None

    def record_crash(self, test_input, error, severity):

        crash_record = {
            "input": test_input,
            "error": error,
            "severity": severity
        }

        self._append_json(self.crashes_file, crash_record)