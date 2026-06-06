import re
from typing import List, Dict, Any


class CrashDeduplicator:

    @staticmethod
    def signature(error_str: str) -> str:
        """
        Normalize an exception message to a dedup key.
        Strips numbers, memory addresses, and variable names to group
        semantically-identical errors together.
        Example: "unsupported operand type(s) for +: 'NoneType' and 'str'"
                 -> "unsupported operand type(s) for +: '<type>' and '<type>'"
        """
        # Normalize type names in quotes
        normalized = re.sub(r"'[^']*'", "'<type>'", error_str)
        # Strip trailing numbers/addresses
        normalized = re.sub(r'\b0x[0-9a-fA-F]+\b', '<addr>', normalized)
        normalized = re.sub(r'\b\d+\b', '<N>', normalized)
        return normalized.strip()

    @staticmethod
    def deduplicate(crashes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Given a list of crash dicts {input, error, severity},
        return one representative per unique (error_type_prefix, normalized_message) pair.
        Keeps the entry with the shortest input (by total character length when serialized).
        """
        seen: Dict[str, Dict[str, Any]] = {}

        for crash in crashes:
            error_str = str(crash.get("error", ""))
            sig = CrashDeduplicator.signature(error_str)
            key = sig

            if key not in seen:
                seen[key] = crash
            else:
                # Keep the one with the shorter input
                existing_len = len(str(seen[key].get("input", "")))
                new_len = len(str(crash.get("input", "")))
                if new_len < existing_len:
                    seen[key] = crash

        return list(seen.values())
