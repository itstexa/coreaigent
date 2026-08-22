"""golden_set.jsonl'a eklenen must_refuse satırları + run_retrieval_eval.py'nin
bunları doğru puanlaması — 2026-08-22 alt-ajan taramasında bulunan boşluk
(docs/IMPROVEMENT_IDEAS.md, Gözlemlenebilirlik #3)."""
from __future__ import annotations

import json
import tempfile

from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.eval.run_retrieval_eval import GOLDEN_SET_PATH
from mevzuat_rag.eval import run_retrieval_eval
from mevzuat_rag.ingestion.local_corpus import load_fixtures


def test_golden_set_has_refuse_cases():
    cases = [json.loads(l) for l in GOLDEN_SET_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    refuse_cases = [c for c in cases if c.get("must_refuse")]
    assert len(refuse_cases) >= 3
    for c in refuse_cases:
        assert c["expected"] == []


def test_run_retrieval_eval_scores_refuse_cases_correctly():
    with tempfile.TemporaryDirectory() as tmp:
        config = RAGConfig.from_env()
        config.qdrant_local_path = tmp
        config.qdrant_collection = "golden_set_refuse_test"
        engine = RAGEngine(config)

        from mevzuat_rag.chunking.chunker import StructureAwareChunker
        from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text

        chunker = StructureAwareChunker(max_tokens=config.chunk_max_tokens)
        for raw_doc in load_fixtures():
            doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
            engine.index_chunks(chunker.chunk(doc))

        result = run_retrieval_eval.run(engine)

        refuse_rows = [r for r in result["per_case"] if r["must_refuse"]]
        assert len(refuse_rows) >= 3
        for row in refuse_rows:
            assert "refused_correctly" in row
            assert "recall@1" not in row  # anlamsız metrik hiç raporlanmamalı

        positive_rows = [r for r in result["per_case"] if not r["must_refuse"]]
        assert len(positive_rows) == 9
        assert all("recall@1" in r for r in positive_rows)

        summary = result["summary"]
        assert "refuse_accuracy" in summary
        assert summary["n_refuse_queries"] == len(refuse_rows)
        # Mevcut kalitenin regresyona uğramadığını da doğrula: pozitif
        # sorularda mükemmel skor korunmalı (bkz. NOTES.md/rapor).
        assert summary["recall@1"] == 1.0
        assert summary["mrr"] == 1.0
