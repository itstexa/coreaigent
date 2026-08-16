"""CLI: local .md fixtures -> parse -> chunk -> embed -> index.

    python -m mevzuat_rag.ingest_pipeline           # one-shot: index everything under sample_data/legislation/
    python -m mevzuat_rag.ingest_pipeline --watch    # keep running, auto re-index on file add/edit

Dropping a new law as a new .md file (or editing an existing one) under
``sample_data/legislation/`` and re-running this is the whole workflow —
no code changes needed. ``load_fixtures()`` globs the directory, so a new
file is picked up automatically. Chunk ids are deterministic per document
(see chunking/chunker.py), and ``RAGEngine.index_chunks`` skips chunks whose
content hash hasn't changed, so re-running after adding one new file only
embeds that file's chunks — it does not re-embed the whole corpus.
"""
from __future__ import annotations

import argparse
import time

from mevzuat_rag.chunking.chunker import StructureAwareChunker
from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.ingestion.local_corpus import SAMPLE_DATA_DIR, load_fixtures


def run(engine: RAGEngine | None = None) -> dict[str, int]:
    engine = engine or RAGEngine()
    chunker = StructureAwareChunker(
        max_tokens=engine.config.chunk_max_tokens,
        overlap_tokens=engine.config.chunk_overlap_tokens,
    )
    totals = {"embedded": 0, "skipped_unchanged": 0}
    for raw_doc in load_fixtures():
        doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
        chunks = chunker.chunk(doc)
        outcome = engine.index_chunks(chunks)
        print(
            f"{raw_doc.kanun_no} ({raw_doc.kanun_adi}): {len(doc.maddeler)} madde, "
            f"{outcome['embedded']} yeni/değişmiş chunk embed edildi, "
            f"{outcome['skipped_unchanged']} değişmemiş chunk atlandı"
        )
        totals["embedded"] += outcome["embedded"]
        totals["skipped_unchanged"] += outcome["skipped_unchanged"]
    print(f"toplam: {totals['embedded']} embed edildi, {totals['skipped_unchanged']} atlandı")
    return totals


def _corpus_fingerprint() -> dict[str, float]:
    return {p.name: p.stat().st_mtime for p in SAMPLE_DATA_DIR.glob("*.md") if p.name.lower() != "readme.md"}


def watch(engine: RAGEngine | None = None, poll_seconds: float = 3.0) -> None:
    engine = engine or RAGEngine()
    print(f"izleniyor: {SAMPLE_DATA_DIR} (her {poll_seconds}s kontrol) — Ctrl+C ile durdur")
    run(engine)
    last_seen = _corpus_fingerprint()
    try:
        while True:
            time.sleep(poll_seconds)
            current = _corpus_fingerprint()
            if current != last_seen:
                changed = sorted(set(current) - set(last_seen) | {k for k in current if current.get(k) != last_seen.get(k)})
                print(f"\ndeğişiklik tespit edildi: {changed}")
                run(engine)
                last_seen = current
    except KeyboardInterrupt:
        print("\nizleme durduruldu")


if __name__ == "__main__":
    args = argparse.ArgumentParser(description="Index local legislation fixtures into Qdrant")
    args.add_argument("--watch", action="store_true", help="klasörü izle, yeni/değişen dosyada otomatik yeniden indeksle")
    args.add_argument("--poll-seconds", type=float, default=3.0)
    parsed = args.parse_args()

    engine = RAGEngine(RAGConfig.from_env())
    if parsed.watch:
        watch(engine, poll_seconds=parsed.poll_seconds)
    else:
        run(engine)
