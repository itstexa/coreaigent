"""CLI: local .md fixtures -> parse -> chunk -> embed -> index, with ingest
timing records written to logs/ so one-shot runs can be compared and failed
chunks are visible as a non-zero exit code.

    python -m mevzuat_rag.ingest_pipeline
    python -m mevzuat_rag.ingest_pipeline --watch

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
import json
import logging
import math
import sys
import time
from datetime import datetime
from pathlib import Path

from mevzuat_rag import metrics
from mevzuat_rag.chunking.chunker import StructureAwareChunker
from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.ingestion.local_corpus import SAMPLE_DATA_DIR, load_fixtures

logger = logging.getLogger(__name__)

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S%f")


def _write_json(file_path: Path, data: object) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    rank = (len(ordered) - 1) * p
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))

    if lower == upper:
        return ordered[lower]

    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def run(engine: RAGEngine | None = None) -> dict[str, object]:
    engine = engine or RAGEngine()
    metrics.clear_records()

    chunker = StructureAwareChunker(
        max_tokens=engine.config.chunk_max_tokens,
        overlap_tokens=engine.config.chunk_overlap_tokens,
    )

    totals = {"embedded": 0, "skipped_unchanged": 0, "failed": 0}
    doc_count = 0
    total_chunks = 0
    parse_ms = 0.0
    chunk_ms = 0.0
    index_ms = 0.0
    model_ms = 0.0
    failed_chunks: list[object] = []

    with metrics.timer("model_load") as t_model:
        _ = engine.model
    model_ms = t_model.duration_ms or 0.0

    with metrics.timer("total") as t_total:
        for raw_doc in load_fixtures():
            doc_count += 1

            with metrics.timer("parse", kanun_no=raw_doc.kanun_no) as t_parse:
                doc = parse_legislation_text(
                    raw_doc.raw_text,
                    raw_doc.kanun_no,
                    raw_doc.kanun_adi,
                    raw_doc.url,
                )
            parse_ms += t_parse.duration_ms or 0.0

            with metrics.timer("chunk", kanun_no=raw_doc.kanun_no) as t_chunk:
                chunks = chunker.chunk(doc)
            chunk_ms += t_chunk.duration_ms or 0.0

            total_chunks += len(chunks)

            with metrics.timer("index_chunks", input_count=len(chunks)) as t_index:
                outcome = engine.index_chunks(chunks)
            index_ms += t_index.duration_ms or 0.0

            embedded = int(outcome.get("embedded", 0))
            skipped = int(outcome.get("skipped_unchanged", 0))
            failed = list(outcome.get("failed") or [])

            totals["embedded"] += embedded
            totals["skipped_unchanged"] += skipped
            totals["failed"] += len(failed)

            logger.info(
                f"{raw_doc.kanun_no} ({raw_doc.kanun_adi}): {len(doc.maddeler)} madde, "
                f"{embedded} yeni/değişmiş chunk embed edildi, "
                f"{skipped} değişmemiş chunk atlandı"
            )

            if failed:
                failed_chunks.extend(failed)

    total_ms = t_total.duration_ms or 0.0
    durations = {
        "total": round(total_ms / 1000.0, 3),
        "model_load": round(model_ms / 1000.0, 3),
        "parse": round(parse_ms / 1000.0, 3),
        "chunk": round(chunk_ms / 1000.0, 3),
        "index_chunks": round(index_ms / 1000.0, 3),
    }

    timestamp = _now_stamp()
    records = metrics.get_records()

    batch_durations = [
        r["duration_ms"]
        for r in records
        if r["stage"] in {"embedding_batch"}
        and isinstance(r.get("duration_ms"), (int, float))
    ]
    p50 = _percentile(batch_durations, 0.50)
    p95 = _percentile(batch_durations, 0.95)

    throughput = total_chunks / durations["total"] if durations["total"] > 0 else 0.0

    summary = {
        "timestamp": timestamp,
        "device": engine.config.embedding_device,
        "documents": doc_count,
        "chunks": total_chunks,
        "totals": totals,
        "duration_s": durations,
        "throughput_chunks_per_s": round(throughput, 3),
        "batch_p50_ms": round(p50, 2) if p50 is not None else None,
        "batch_p95_ms": round(p95, 2) if p95 is not None else None,
        "records": records,
    }

    _write_json(LOGS_DIR / f"ingest_run_{timestamp}.json", summary)

    if failed_chunks:
        failed_path = LOGS_DIR / f"failed_chunks_{timestamp}.json"
        _write_json(failed_path, failed_chunks)
        logger.warning("Başarısız chunk listesi yazıldı: %s", failed_path)

    embed_share = (
        durations["index_chunks"] / durations["total"] * 100
        if durations["total"] > 0
        else 0.0
    )
    p50_text = f"{p50:.0f}ms" if p50 is not None else "-"
    p95_text = f"{p95:.0f}ms" if p95 is not None else "-"

    logger.info("Ingest tamamlandı")
    logger.info(
        f"  Doküman: {doc_count} | Chunk: {total_chunks} | Embed: {totals['embedded']} | "
        f"Atlanan: {totals['skipped_unchanged']} | Başarısız: {totals['failed']}"
    )
    logger.info(f"  Toplam süre: {durations['total']:.1f}s")
    logger.info(
        f"  Embedding+Store: {durations['index_chunks']:.1f}s ({embed_share:.0f}%) | "
        f"Parse: {durations['parse']:.1f}s | Chunk: {durations['chunk']:.1f}s"
    )
    logger.info(
        f"  Verim: {throughput:.1f} chunk/s | Batch p50: {p50_text} | p95: {p95_text}"
    )
    logger.info(
        f"  Model yükleme: {durations['model_load']:.1f}s | Device: {engine.config.embedding_device}"
    )

    return summary


def _corpus_fingerprint() -> dict[str, float]:
    return {
        p.name: p.stat().st_mtime
        for p in SAMPLE_DATA_DIR.glob("*.md")
        if p.name.lower() != "readme.md"
    }


def watch(engine: RAGEngine | None = None, poll_seconds: float = 3.0) -> None:
    engine = engine or RAGEngine()
    logger.info(
        "izleniyor: %s (her %ss kontrol) — Ctrl+C ile durdur",
        SAMPLE_DATA_DIR,
        poll_seconds,
    )

    summary = run(engine)
    if summary["totals"]["failed"]:
        logger.warning("Başarısız chunk var; ayrıntı logs/failed_chunks_*.json dosyasında.")

    last_seen = _corpus_fingerprint()
    try:
        while True:
            time.sleep(poll_seconds)
            current = _corpus_fingerprint()
            if current != last_seen:
                changed = sorted(
                    set(current) - set(last_seen)
                    | {k for k in current if current.get(k) != last_seen.get(k)}
                )
                logger.info("değişiklik tespit edildi: %s", changed)
                summary = run(engine)
                if summary["totals"]["failed"]:
                    logger.warning(
                        "Başarısız chunk var; ayrıntı logs/failed_chunks_*.json dosyasında."
                    )
                last_seen = current
    except KeyboardInterrupt:
        logger.info("izleme durduruldu")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Index local legislation fixtures into Qdrant"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="klasörü izle, yeni/değişen dosyada otomatik yeniden indeksle",
    )
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parsed = parser.parse_args()

    engine = RAGEngine(RAGConfig.from_env())
    if parsed.watch:
        watch(engine, poll_seconds=parsed.poll_seconds)
        sys.exit(0)

    run_summary = run(engine)
    sys.exit(1 if run_summary.get("totals", {}).get("failed", 0) else 0)
