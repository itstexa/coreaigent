"""Turns a parsed LegislationDocument into citation-carrying chunks.

Invariant: a chunk never splits a fıkra/bent in half. When consecutive
fıkralar of the same madde fit within ``max_tokens`` they're merged into one
chunk (reduces fragmentation for short maddeler); a single fıkra longer than
``max_tokens`` becomes its own chunk regardless (never truncated — legal text
must not be silently cut).
"""
from __future__ import annotations

import hashlib
import uuid

from mevzuat_rag.models import ChunkMetadata, LegislationChunk, LegislationDocument
from mevzuat_rag.text_norm import normalize_text
from mevzuat_rag.token_estimate import estimate_tokens as _estimate_tokens


def _citation(kanun_no: str, kanun_adi: str, madde_no: int, fikra_no: int | None, bent: str | None) -> str:
    parts = [f"{kanun_no} sayılı {kanun_adi}", f"Madde {madde_no}"]
    if fikra_no is not None:
        parts.append(f"Fıkra {fikra_no}")
    if bent is not None:
        parts.append(f"Bent ({bent})")
    return ", ".join(parts)


def _source_hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


class StructureAwareChunker:
    def __init__(self, max_tokens: int = 768, overlap_tokens: int = 80):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, doc: LegislationDocument) -> list[LegislationChunk]:
        chunks: list[LegislationChunk] = []
        for madde in doc.maddeler:
            buffer_text: list[str] = []
            buffer_tokens = 0
            buffer_first_fikra: int | None = None
            buffer_last_fikra: int | None = None

            def flush() -> None:
                nonlocal buffer_text, buffer_tokens, buffer_first_fikra, buffer_last_fikra
                if not buffer_text:
                    return
                text = normalize_text("\n".join(buffer_text), profile="embedding")
                fikra_label = buffer_first_fikra
                if buffer_first_fikra != buffer_last_fikra:
                    fikra_label = None  # spans multiple fıkralar; citation stays at madde level
                metadata = ChunkMetadata(
                    kanun_no=doc.kanun_no,
                    kanun_adi=doc.kanun_adi,
                    madde_no=madde.madde_no,
                    fikra_no=fikra_label,
                    bent=None,
                    kaynak_url=doc.kaynak_url,
                    source_hash=_source_hash(doc.kanun_no, str(madde.madde_no), text),
                    durum=madde.durum,
                )
                chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc.kanun_no}:{madde.madde_no}:{buffer_first_fikra}:{len(chunks)}"))
                chunks.append(LegislationChunk(
                    id=chunk_id,
                    text=text,
                    metadata=metadata,
                    citation=_citation(doc.kanun_no, doc.kanun_adi, madde.madde_no, fikra_label, None),
                ))
                buffer_text = []
                buffer_tokens = 0
                buffer_first_fikra = None
                buffer_last_fikra = None

            for fikra in madde.fikralar:
                label = f"({fikra.fikra_no})" + (f" {fikra.bent})" if fikra.bent else "")
                unit_text = normalize_text(f"{label} {fikra.text}".strip(), profile="embedding")
                unit_tokens = _estimate_tokens(unit_text)

                if unit_tokens > self.max_tokens:
                    flush()
                    metadata = ChunkMetadata(
                        kanun_no=doc.kanun_no, kanun_adi=doc.kanun_adi, madde_no=madde.madde_no,
                        fikra_no=fikra.fikra_no, bent=fikra.bent, kaynak_url=doc.kaynak_url,
                        source_hash=_source_hash(doc.kanun_no, str(madde.madde_no), str(fikra.fikra_no), unit_text),
                        durum=madde.durum,
                    )
                    chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc.kanun_no}:{madde.madde_no}:{fikra.fikra_no}:{fikra.bent}:{len(chunks)}"))
                    chunks.append(LegislationChunk(
                        id=chunk_id, text=unit_text, metadata=metadata,
                        citation=_citation(doc.kanun_no, doc.kanun_adi, madde.madde_no, fikra.fikra_no, fikra.bent),
                    ))
                    continue

                if buffer_tokens + unit_tokens > self.max_tokens:
                    flush()

                buffer_text.append(unit_text)
                buffer_tokens += unit_tokens
                if buffer_first_fikra is None:
                    buffer_first_fikra = fikra.fikra_no
                buffer_last_fikra = fikra.fikra_no

            flush()

        return chunks
