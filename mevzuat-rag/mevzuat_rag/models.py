"""Data shapes shared across the mevzuat_rag pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChunkMetadata:
    kanun_no: str
    kanun_adi: str
    madde_no: int | None
    fikra_no: int | None
    bent: str | None
    kaynak_url: str
    source_hash: str


@dataclass
class LegislationChunk:
    id: str
    text: str
    metadata: ChunkMetadata
    citation: str


@dataclass
class RetrievalResult:
    chunk: LegislationChunk
    score: float


@dataclass
class LegislationDocument:
    kanun_no: str
    kanun_adi: str
    kaynak_url: str
    maddeler: list["MaddeNode"] = field(default_factory=list)


@dataclass
class FikraNode:
    fikra_no: int
    bent: str | None
    text: str


@dataclass
class MaddeNode:
    madde_no: int
    baslik: str | None
    fikralar: list[FikraNode] = field(default_factory=list)
