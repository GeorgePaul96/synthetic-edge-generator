from dataclasses import dataclass
from typing import Tuple, Type


@dataclass
class FuzzContract:
    allowed_exceptions: Tuple[Type[Exception], ...] = ()
    crash_exceptions: Tuple[Type[Exception], ...] = (
        MemoryError,
        SystemError,
        RuntimeError,
    )


def fuzz_contract(allowed_exceptions=()):
    def decorator(func):
        func._fuzz_contract = FuzzContract(
            allowed_exceptions=allowed_exceptions
        )
        return func
    return decorator