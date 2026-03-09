"""
string_handler.py

Production-grade string edge case generator.

Design goals:
• Encoding edge cases
• Null-byte injection
• Unicode edge cases
• Length boundary stress
• Injection patterns
"""


class StringHandler:

    def generate_edge_cases(self):

        return [

            # Empty / whitespace
            "",
            " ",
            "\t",
            "\n",
            "\r\n",

            # Null byte
            "\0",

            # Unicode
            "🔥",
            "∞",
            "你好",
            "𠜎",

            # Long strings
            "A" * 10,
            "A" * 100,
            "A" * 1000,

            # Numeric strings
            "0",
            "-1",
            "1.0",

            # Injection patterns
            "' OR 1=1 --",
            "<script>alert(1)</script>",

            # Invalid types
            None,
            123,
            True,
        ]