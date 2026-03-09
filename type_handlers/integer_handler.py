"""
integer_handler.py

Production-grade integer edge case generator.

Design goals:
• Boundary probing
• Overflow probing
• Arbitrary precision probing
• Type confusion probing
• Mutation-friendly inputs
"""

import sys


class IntegerHandler:

    def generate_edge_cases(self):

        return [

            # Core values
            0,
            1,
            -1,

            # System boundaries
            sys.maxsize,
            -sys.maxsize - 1,

            # Boundary transitions
            sys.maxsize + 1,
            -sys.maxsize - 2,

            # Bit boundaries
            2**31 - 1,
            -2**31,

            2**63 - 1,
            -2**63,

            # Arbitrary precision stress
            10**100,
            -10**100,

            # Powers of two
            2**8,
            2**16,
            2**32,
            2**64,

            # Special values for logic errors
            None,
            True,
            False,

            # Invalid types (intentional)
            "0",
            "integer",
            1.0,
        ]