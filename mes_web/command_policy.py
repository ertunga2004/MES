from __future__ import annotations


def is_local_only_command(kind: str, value: str) -> bool:
    return kind == "preset" and value == "__reset_counts__"
