"""Hard-negative eval entegrasyon testi — gerçek corpus, gerçek embedding,
gerçek reranker, gerçek Qdrant (LLM yok, retrieve() yeterli).

docs/IMPROVEMENT_IDEAS.md'deki "Retrieval #4 — Hard-negative eval seti"
fikrinin uygulamasının testi: mevzuat_rag/eval/run_hard_negative_eval.py'nin
gerçekten çalıştığını ve mantıklı bir discrimination_accuracy/margin
ürettiğini kanıtlar.
"""
from __future__ import annotations

import tempfile

from mevzuat_rag.chunking.chunker import StructureAwareChunker
from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.eval import run_hard_negative_eval
from mevzuat_rag.ingestion.local_corpus import load_fixtures


def _make_engine(tmp_qdrant: str) -> RAGEngine:
    config = run_hard_negative_eval._default_config()
    config.qdrant_local_path = tmp_qdrant
    config.qdrant_collection = "hard_negative_eval_test"
    engine = RAGEngine(config)

    chunker = StructureAwareChunker(max_tokens=config.chunk_max_tokens)
    for raw_doc in load_fixtures():
        doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
        engine.index_chunks(chunker.chunk(doc))
    return engine


def test_hard_negative_eval_runs_and_reports_discrimination():
    with tempfile.TemporaryDirectory() as tmp:
        engine = _make_engine(tmp)
        result = run_hard_negative_eval.run(engine)

    summary = result["summary"]
    assert summary["n_pairs"] == len(result["per_case"])
    assert summary["n_pairs"] >= 5, "hard_negatives.jsonl'da en az 5-6 örnek olmalı"
    assert 0.0 <= summary["discrimination_accuracy"] <= 1.0

    for row in result["per_case"]:
        assert row["correct"] != row["hard_negative"], "doğru ve hard-negative madde aynı olamaz"
        assert row["discriminated"] == (row["margin"] > 0)
        # Not tam eşitlik: margin, YUVARLANMAMIŞ skorlardan hesaplanıyor;
        # burada zaten yuvarlanmış correct_score/hard_negative_score'u
        # tekrar çıkarıp yuvarlamak çifte-yuvarlama farkı (±0.0001)
        # üretebilir — bu bir hata değil, kayan nokta aritmetiğinin doğası.
        assert abs(row["margin"] - round(row["correct_score"] - row["hard_negative_score"], 4)) < 0.001
        assert row["reason"], "her satırın karışabilirlik gerekçesi olmalı"


def test_hard_negative_eval_discriminates_madde6_vs_madde5():
    """Görev tanımındaki kendi örneği: reranker gerçekten Madde 6'yı (hangi
    dilekçeler incelenemez) Madde 5'in (yanlış makama verilme) önüne koyuyor
    mu, yoksa iki maddenin yüzeysel benzerliği (dilekçe + idari makam teması)
    reranker'ı kandırıyor mu?"""
    with tempfile.TemporaryDirectory() as tmp:
        engine = _make_engine(tmp)
        result = run_hard_negative_eval.run(engine)

    case = next(r for r in result["per_case"] if r["correct"] == "3071:6" and r["hard_negative"] == "3071:5")
    assert case["discriminated"], f"reranker Madde 6'yı Madde 5'ten ayırt edemedi: {case}"
    assert case["correct_score"] > case["hard_negative_score"]


if __name__ == "__main__":
    import unittest

    unittest.main()
