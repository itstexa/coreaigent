"""Candidate — the unit that flows through the retrieval pipeline stages.

Wraps a LegislationChunk + retrieval score with the bookkeeping the pipeline
needs (which stage produced it, its parent section id for [4] Parent
Document Retrieval, free-form per-stage metadata). LegislationChunk /
RetrievalResult (models.py) stay the storage-layer contract, unchanged —
Candidate is only used inside the pipeline, converting to/from
RetrievalResult at the RAGEngine boundary so retrieve()/ask() keep their
existing return types.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from mevzuat_rag.models import LegislationChunk, RetrievalResult


@dataclass
class Candidate:
    id: str
    text: str
    score: float
    source: str  # "dense" | "bm25" | "fused" | "reranked" | "hyde"
    parent_id: str | None
    metadata: dict = field(default_factory=dict)
    chunk: LegislationChunk | None = None

    @classmethod
    def from_result(cls, result: RetrievalResult, source: str = "dense") -> "Candidate":
        return cls(
            id=result.chunk.id,
            text=result.chunk.text,
            score=result.score,
            source=source,
            parent_id=None,
            chunk=result.chunk,
        )

    def to_result(self) -> RetrievalResult:
        return RetrievalResult(chunk=self.chunk, score=self.score)
