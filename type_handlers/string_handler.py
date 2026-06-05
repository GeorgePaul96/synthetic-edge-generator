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
            "\n",
            "\t",
            "\r\n",

            # Long string
            "a" * 1000,

            # Numeric strings
            "0",
            "-1",

            # Special string values
            "None",

            # Null byte
            "\x00",

            # Unicode
            "café",
            "𠜎",

            # Injection patterns
            "<script>",
        ]
