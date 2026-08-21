"""Uçtan uca entegrasyon: PDF -> PII redaksiyon -> parse -> chunk -> embed ->
Qdrant. Gerçek embedding modeli kullanır (GPU varsa GPU, yoksa CPU) — mock
yok, bu yüzden test_smoke_pipeline.py'den daha yavaş ama gerçek ingest
yolunun uçtan uca çalıştığını kanıtlıyor.

TCKN test sabiti (11111111110) sentetik/uydurmadır (bkz. test_pii.py).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz", reason="PyMuPDF yalnızca test fixture PDF üretimi için gerekli, runtime bağımlılığı değil")

from mevzuat_rag import ingest_pipeline
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.ingestion.pdf_corpus import load_pdf_corpus


def _make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text, fontsize=10)
    doc.save(str(path))
    doc.close()


def test_pdf_to_index_end_to_end(tmp_path: Path):
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    _make_pdf(
        pdf_dir / "test_kanunu.pdf",
        "MADDE 1- Basvuru sahibinin TCKN numarasi 11111111110 olarak kayda gecer.\n"
        "MADDE 2- Iletisim telefonu 05321234567 numarasidir.",
    )
    checkpoint = tmp_path / "checkpoint.jsonl"

    with tempfile.TemporaryDirectory() as tmp_qdrant:
        config = RAGConfig.from_env()
        config.qdrant_local_path = tmp_qdrant
        config.qdrant_collection = "pdf_ingest_e2e_test"
        engine = RAGEngine(config)

        docs = load_pdf_corpus(pdf_dir, checkpoint, workers=1)
        summary = ingest_pipeline.run(engine, documents=docs, flush_every=1)

        assert summary["documents"] == 1
        assert summary["chunks"] >= 2
        assert summary["totals"]["embedded"] >= 2
        assert summary["totals"]["failed"] == 0

        # Store'daki chunk metinlerinde ham TCKN/telefon asla görünmemeli —
        # redaksiyon PDF worker'ında, chunklamadan/embed'lemeden önce oldu.
        hits = engine.store.search(engine.model.encode(["TCKN telefon"])[0], top_k=10)
        all_text = " ".join(h.chunk.text for h in hits)
        assert "11111111110" not in all_text
        assert "05321234567" not in all_text
        assert "[TCKN]" in all_text or "[TELEFON]" in all_text

        # logs/ altına ara kayıt (flush_every=1) gerçekten yazılmış olmalı.
        partial_logs = list(ingest_pipeline.LOGS_DIR.glob(f"ingest_partial_{summary['timestamp'][:8]}*"))
        assert len(partial_logs) >= 1
        for p in partial_logs:
            p.unlink()
