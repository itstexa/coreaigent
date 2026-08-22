"""BM25 invalidate() ingest sırasında dokümanda bir değil, batch başına bir
kez çağrılmalı — 2026-08-22 alt-ajan taramasında bulunan gerçek risk (bkz.
docs/IMPROVEMENT_IDEAS.md, "Ölçek ve Performans #1"): aynı RAGEngine
eşzamanlı sorgu da sunuyorsa, her ingest edilen dokümanın hemen ardından
gelen sorgu tüm corpus'u yeniden taramak zorunda kalıyordu.
"""
from __future__ import annotations

import tempfile
from unittest.mock import patch

from mevzuat_rag import ingest_pipeline
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.ingestion.local_corpus import load_fixtures


def test_batch_ingest_invalidates_bm25_once_not_per_document():
    with tempfile.TemporaryDirectory() as tmp:
        config = RAGConfig.from_env()
        config.qdrant_local_path = tmp
        config.qdrant_collection = "bm25_batch_invalidate_test"
        engine = RAGEngine(config)

        docs = load_fixtures()
        assert len(docs) >= 2, "bu test birden fazla doküman gerektiriyor — batching'i kanıtlamak için"

        with patch.object(engine.bm25_index, "invalidate", wraps=engine.bm25_index.invalidate) as spy:
            summary = ingest_pipeline.run(engine, documents=iter(docs))
            assert summary["documents"] == len(docs)
            assert summary["totals"]["embedded"] > 0
            assert spy.call_count == 1, (
                f"{len(docs)} doküman ingest edildi ama invalidate() {spy.call_count} kez çağrıldı — "
                "batch başına 1 olmalıydı"
            )


def test_bm25_still_correct_after_batched_invalidation():
    """Ertelenmiş invalidation, ilk sorguda BM25'in eksiksiz/doğru
    kurulmasını engellememeli — tüm corpus tek seferde indekslenmiş olmalı."""
    with tempfile.TemporaryDirectory() as tmp:
        config = RAGConfig.from_env()
        config.qdrant_local_path = tmp
        config.qdrant_collection = "bm25_batch_correctness_test"
        engine = RAGEngine(config)

        ingest_pipeline.run(engine, documents=iter(load_fixtures()))

        hits = engine.bm25_index.search("dilekçe", top_k=5, store=engine.store)
        assert len(hits) > 0, "batch ingest sonrası BM25 aramasında sonuç bulunamadı"


def test_index_chunks_default_still_invalidates_immediately():
    """Geriye dönük uyumluluk: invalidate_bm25 parametresi verilmezse eski
    davranış (her çağrıda hemen invalidate) korunmalı — mevcut çağıran
    kodlar (ör. tekil chunk ekleme senaryoları) bozulmamalı."""
    with tempfile.TemporaryDirectory() as tmp:
        config = RAGConfig.from_env()
        config.qdrant_local_path = tmp
        config.qdrant_collection = "bm25_default_behavior_test"
        engine = RAGEngine(config)

        from mevzuat_rag.chunking.chunker import StructureAwareChunker
        from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text

        chunker = StructureAwareChunker(max_tokens=config.chunk_max_tokens)
        raw_doc = load_fixtures()[0]
        doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
        chunks = chunker.chunk(doc)

        with patch.object(engine.bm25_index, "invalidate", wraps=engine.bm25_index.invalidate) as spy:
            engine.index_chunks(chunks)  # invalidate_bm25 verilmedi -> varsayılan True
            assert spy.call_count == 1
