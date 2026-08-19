"""Shared exception types. Split out from engine.py so pipeline stages can
raise RAGError without importing engine.py (which imports the stages —
would otherwise be a circular import).
"""
from __future__ import annotations


class RAGError(Exception):
    def __init__(self, message: str, category: str = "validation"):
        super().__init__(message)
        self.category = category


class GenerationError(Exception):
    pass
