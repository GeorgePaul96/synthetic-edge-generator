import random
import sys
from typing import Iterator

from type_handlers.base import Handler


class FloatHandler(Handler):
    _SPECIALS = (0.0, -0.0, float("inf"), float("-inf"), float("nan"),
                 sys.float_info.max, sys.float_info.min)

    def generate(self, rng, budget):
        if rng.random() < 0.25:
            return rng.choice(self._SPECIALS)
        return rng.uniform(-1e6, 1e6)

    def edge_cases(self) -> Iterator:
        for v in self._SPECIALS:
            yield v

    def type_sig(self) -> str:
        return "float"

    def descriptor(self) -> dict:
        return {"k": "float"}


class IntegerHandler(Handler):
    _EDGE = (0, 1, -1, sys.maxsize, -sys.maxsize - 1, 2**31 - 1, -2**31,
             2**63 - 1, -2**63, 10**18)

    def generate(self, rng, budget):
        if rng.random() < 0.25:
            return rng.choice(self._EDGE)
        return rng.randint(-(2**32), 2**32)

    def edge_cases(self) -> Iterator:
        for v in self._EDGE:
            yield v

    def type_sig(self) -> str:
        return "int"

    def descriptor(self) -> dict:
        return {"k": "int"}


class StringHandler(Handler):
    _EDGE = ("", " ", "\t", "\n", "\0", "🔥", "你好", "' OR 1=1 --", "<script>alert(1)</script>")
    _ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789 _-"

    def generate(self, rng, budget):
        if rng.random() < 0.25:
            return rng.choice(self._EDGE)[: budget.max_string_length]
        n = rng.randint(0, budget.max_string_length)
        return "".join(rng.choice(self._ALPHABET) for _ in range(n))

    def edge_cases(self) -> Iterator:
        for v in self._EDGE:
            yield v

    def type_sig(self) -> str:
        return "str"

    def descriptor(self) -> dict:
        return {"k": "str"}


class BoolHandler(Handler):
    def generate(self, rng, budget):
        return rng.choice([True, False])

    def edge_cases(self) -> Iterator:
        yield True
        yield False

    def type_sig(self) -> str:
        return "bool"

    def descriptor(self) -> dict:
        return {"k": "bool"}


class NoneHandler(Handler):
    def generate(self, rng, budget):
        return None

    def edge_cases(self) -> Iterator:
        yield None

    def type_sig(self) -> str:
        return "None"

    def descriptor(self) -> dict:
        return {"k": "none"}
