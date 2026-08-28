"""Managed RAG source validation and deterministic corpus primitives."""

from __future__ import annotations

import math
from pathlib import PurePosixPath


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_CHUNK_CHARACTERS = 3000
EMBEDDING_DIMENSION = 1024
VECTOR_NORM_TOLERANCE = 0.001
SUPPORTED_UPLOADS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class RagSourceError(ValueError):
    """A controlled source validation failure with a stable machine code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def validate_upload(filename: str, content_type: str, content: bytes) -> tuple[str, str, int]:
    """Validate the byte boundary before any OCR, storage, or embedding work."""
    suffix = PurePosixPath(filename or "").suffix.lower()
    if not filename or len(filename) > 255 or SUPPORTED_UPLOADS.get(suffix) != content_type:
        raise RagSourceError("FILE_TYPE_INVALID", "Only matching PDF and DOCX uploads are accepted")
    if not content:
        raise RagSourceError("FILE_EMPTY", "The source file must not be empty")
    if len(content) > MAX_FILE_BYTES:
        raise RagSourceError("FILE_TOO_LARGE", "The source file exceeds 10 MiB")
    return filename, content_type, len(content)


def chunk_text(text: str) -> list[str]:
    """Partition normalized text without omission or overlap."""
    if not text:
        raise RagSourceError("TEXT_EMPTY", "Normalized text must not be empty")
    return [text[offset : offset + MAX_CHUNK_CHARACTERS] for offset in range(0, len(text), MAX_CHUNK_CHARACTERS)]


def validate_vector(vector: list[float]) -> list[float]:
    """Reject mixed spaces before a source can become searchable."""
    if len(vector) != EMBEDDING_DIMENSION:
        raise RagSourceError("VECTOR_DIMENSION_INVALID", "Embedding must contain exactly 1024 dimensions")
    if not all(math.isfinite(value) for value in vector):
        raise RagSourceError("VECTOR_INVALID", "Embedding values must be finite")
    norm = math.sqrt(sum(value * value for value in vector))
    if abs(norm - 1.0) > VECTOR_NORM_TOLERANCE:
        raise RagSourceError("VECTOR_NORM_INVALID", "Embedding must be L2 normalized")
    return vector
