"""Unit tests for mevzuat_rag.

Parser/chunker/retrieval tests always run (retrieval needs the local BGE-M3
model + embedded Qdrant, both available offline). The generation test hits
the real DeepSeek API and is skipped automatically if DEEPSEEK_API_KEY isn't
set, so the rest of the suite stays runnable without a key/network.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from mevzuat_rag.chunking.chunker import StructureAwareChunker
from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.ingestion.local_corpus import load_fixtures

SAMPLE_TEXT = """MADDE 6- Türkiye Büyük Millet Meclisine veya yetkili makamlara verilen veya gönderilen dilekçelerden;
a) Belli bir konuyu ihtiva etmeyenler,
b) Yargı mercilerinin görevine giren konularla ilgili olanlar,
incelenemezler.

MADDE 7- (1) Başvurunun sonucu otuz gün içinde bildirilir.
(2) İşlem safahatının duyurulması halinde alınan sonuç ayrıca bildirilir.
"""


def _fresh_engine(collection: str, tmp_path: str) -> RAGEngine:
    config = RAGConfig.from_env()
    config.qdrant_local_path = tmp_path
    config.qdrant_collection = collection
    return RAGEngine(config)


class LegalStructureParserTests(unittest.TestCase):
    def test_parses_madde_bent_without_explicit_fikra(self):
        doc = parse_legislation_text(SAMPLE_TEXT, "3071", "Dilekçe Kanunu", "https://example.test")
        madde6 = next(m for m in doc.maddeler if m.madde_no == 6)
        bents = [f for f in madde6.fikralar if f.bent is not None]
        self.assertEqual([b.bent for b in bents], ["a", "b"])
        self.assertIn("Yargı mercilerinin", bents[1].text)

    def test_parses_numbered_fikralar(self):
        doc = parse_legislation_text(SAMPLE_TEXT, "3071", "Dilekçe Kanunu", "https://example.test")
        madde7 = next(m for m in doc.maddeler if m.madde_no == 7)
        self.assertEqual([f.fikra_no for f in madde7.fikralar], [1, 2])
        self.assertIn("otuz gün", madde7.fikralar[0].text)


class StructureAwareChunkerTests(unittest.TestCase):
    def test_never_splits_a_bent_even_under_tight_token_budget(self):
        doc = parse_legislation_text(SAMPLE_TEXT, "3071", "Dilekçe Kanunu", "https://example.test")
        chunks = StructureAwareChunker(max_tokens=8, overlap_tokens=0).chunk(doc)
        madde6 = next(m for m in doc.maddeler if m.madde_no == 6)
        for bent in (f for f in madde6.fikralar if f.bent is not None):
            self.assertTrue(any(bent.text in c.text for c in chunks), bent.text)

    def test_citation_includes_kanun_and_madde(self):
        doc = parse_legislation_text(SAMPLE_TEXT, "3071", "Dilekçe Kanunu", "https://example.test")
        chunks = StructureAwareChunker(max_tokens=768).chunk(doc)
        self.assertTrue(all("3071 sayılı Dilekçe Kanunu" in c.citation and "Madde" in c.citation for c in chunks))


class RAGEngineTests(unittest.TestCase):
    def test_retrieve_returns_relevant_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _fresh_engine("test_mevzuat_chunks", tmp)
            chunker = StructureAwareChunker(max_tokens=engine.config.chunk_max_tokens)
            for raw_doc in load_fixtures():
                doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
                engine.index_chunks(chunker.chunk(doc))

            hits = engine.retrieve("Dilekçe hakkının amacı nedir?")
            self.assertTrue(hits)
            self.assertIn("3071", hits[0].chunk.citation)

    def test_reindexing_unchanged_chunks_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _fresh_engine("test_reindex_skip", tmp)
            raw_doc = load_fixtures()[0]
            doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
            chunks = StructureAwareChunker(max_tokens=engine.config.chunk_max_tokens).chunk(doc)

            first_run = engine.index_chunks(chunks)
            self.assertEqual(first_run["embedded"], len(chunks))
            second_run = engine.index_chunks(chunks)
            self.assertEqual(second_run["embedded"], 0)
            self.assertEqual(second_run["skipped_unchanged"], len(chunks))


@unittest.skipUnless(os.environ.get("DEEPSEEK_API_KEY"), "DEEPSEEK_API_KEY not set")
class GenerationTests(unittest.TestCase):
    def test_ask_refuses_to_answer_outside_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = _fresh_engine("test_generation", tmp)
            chunker = StructureAwareChunker(max_tokens=engine.config.chunk_max_tokens)
            for raw_doc in load_fixtures():
                doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
                engine.index_chunks(chunker.chunk(doc))

            # Not: "elektronik imza/sertifika" artık corpus İÇİNDE (2646 sayılı
            # Yönetmelik Madde 3/4/17, offline_docs ile eklendi) — o yüzden
            # gerçekten corpus dışı, farklı bir kanuna ait bir soru kullanılıyor.
            result = engine.ask("2577 sayılı İdari Yargılama Usulü Kanunu'na göre dava açma süresi kaç gündür?")
            self.assertIn("cevabı yok", result["answer"].lower())


if __name__ == "__main__":
    unittest.main()
