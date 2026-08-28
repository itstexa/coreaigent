"""Falsification tests for the local mevzuat-rag hybrid retrieval adapter."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "workflow"))

from hybrid_retrieval import bm25_scores, fuse_chunks, tokenize_tr  # noqa: E402


class HybridRetrievalTests(unittest.TestCase):
    def test_turkish_tokenization_keeps_legal_terms_and_removes_connectors(self):
        self.assertEqual(tokenize_tr("İdare ve dilekçe hakkı"), ["idare", "dilekçe", "hakkı"])
        self.assertEqual(tokenize_tr("3071 sayılı Kanun kapsamında"), ["3071"])

    def test_exact_term_scores_above_unrelated_chunk(self):
        scores = bm25_scores("3071 dilekçe kanunu", ["3071 sayılı Dilekçe Hakkı Kanunu", "Belediye temizlik hizmeti"])
        self.assertGreater(scores[0], scores[1])
        self.assertEqual(scores[1], 0.0)

    def test_fusion_uses_lexical_rank_without_replacing_dense_citation_score(self):
        chunks = [{"chunk_id": "semantic", "content": "belediye hizmetleri"}, {"chunk_id": "law", "content": "3071 sayılı dilekçe kanunu"}]
        fused = fuse_chunks(chunks, [0.8, 0.4], "3071 dilekçe kanunu")
        law = next(item for item in fused if item["chunk_id"] == "law")
        self.assertEqual(law["score"], 0.4)
        self.assertEqual(law["lexical_score"], 1.0)
        self.assertGreater(law["rank_score"], 0.0)
