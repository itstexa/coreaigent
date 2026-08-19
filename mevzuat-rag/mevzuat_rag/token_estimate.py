"""Shared token-count estimate — chars/4 heuristic, avoids pulling in a real
tokenizer dependency just to gate stage triggers (HyDE's trigger_max_tokens)
and budget checks (chunking, compression, parent-doc token budgets)."""
from __future__ import annotations

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)
