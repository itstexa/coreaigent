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


class EmbeddingError(RAGError):
    def __init__(
        self,
        message: str,
        *,
        cause: Exception | None = None,
        context: dict | None = None,
    ):
        super().__init__(message, category="embedding")
        self.cause = cause
        self.context = context or {}


class EmbeddingModelLoadError(EmbeddingError):
    pass


class EmbeddingComputeError(EmbeddingError):
    pass


class EmbeddingInputError(EmbeddingError):
    pass


class EmbeddingDimensionError(EmbeddingError):
    pass


class EmbeddingOOMError(EmbeddingError):
    pass
