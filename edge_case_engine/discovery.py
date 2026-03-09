"""
discovery.py

Automatic fuzz target discovery using fuzz_contract metadata.

This module scans Python modules and discovers functions that have been
decorated with @fuzz_contract.

This enables scalable fuzzing without manual target registration.

Production design goals:
• Deterministic discovery
• Zero manual wiring
• Contract-driven execution
• Extensible for plugin systems
"""

import inspect
import types
from dataclasses import dataclass
from typing import Callable, List, Tuple, Dict, Any


@dataclass(frozen=True)
class FuzzTarget:
    """
    Immutable representation of a fuzz target.
    """

    function: Callable
    name: str
    module: str
    parameters: Tuple[str, ...]
    contract: Dict[str, Any]


class TargetDiscovery:
    """
    Discovers fuzz targets from modules.
    """

    CONTRACT_ATTR = "__fuzz_contract__"

    @classmethod
    def discover_module(cls, module: types.ModuleType) -> List[FuzzTarget]:
        """
        Discover fuzz targets inside a module.

        Args:
            module: imported module

        Returns:
            list of FuzzTarget objects
        """

        targets = []

        for name, obj in inspect.getmembers(module):

            if not inspect.isfunction(obj):
                continue

            contract = getattr(obj, cls.CONTRACT_ATTR, None)

            if contract is None:
                continue

            signature = inspect.signature(obj)

            parameters = tuple(signature.parameters.keys())

            target = FuzzTarget(
                function=obj,
                name=obj.__name__,
                module=obj.__module__,
                parameters=parameters,
                contract=contract,
            )

            targets.append(target)

        return targets

    @classmethod
    def discover_modules(cls, modules: List[types.ModuleType]) -> List[FuzzTarget]:
        """
        Discover fuzz targets from multiple modules.
        """

        all_targets = []

        for module in modules:
            targets = cls.discover_module(module)
            all_targets.extend(targets)

        return all_targets