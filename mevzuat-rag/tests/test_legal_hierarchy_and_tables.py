"""Mevzuat hiyerarşisi (mevzuat_turu) ve tablo/ek uyarı bayrağı
(contains_table) testleri.

Bu iki alan da ChunkMetadata.durum'un izinden gidiyor: durum store.py'de
daha önce yazma/okuma senkronizasyonu unutulduğu için sessizce varsayılana
düşen bir bug'a sebep olmuştu (bkz. models.py'deki ChunkMetadata.durum
yorumu, docs/IMPROVEMENT_IDEAS.md). Bu dosyadaki round-trip testi tam olarak
o hatanın mevzuat_turu/contains_table için TEKRARLANMADIĞINI kanıtlamak
için var — bellek-içi nesne testleri tek başına yeterli değil, gerçek bir
Qdrant upsert + geri okuma gerekiyor.

sample_data/legislation/ içindeki 2 gerçek belgede tablo örneği YOK (corpus
küçük/temiz) — contains_table testleri bu yüzden sentetik metinlerle
yazıldı, dürüstçe not edilmiştir.
"""
from __future__ import annotations

import tempfile
import unittest

from mevzuat_rag.chunking.chunker import StructureAwareChunker
from mevzuat_rag.chunking.legal_structure_parser import (
    _infer_mevzuat_turu,
    _looks_like_table_line,
    parse_legislation_text,
)
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.generation import SYSTEM_PROMPT, _build_context
from mevzuat_rag.ingestion.local_corpus import load_fixtures
from mevzuat_rag.models import ChunkMetadata, LegislationChunk, RetrievalResult


def _fresh_engine(collection: str, tmp_path: str) -> RAGEngine:
    config = RAGConfig.from_env()
    config.qdrant_local_path = tmp_path
    config.qdrant_collection = collection
    return RAGEngine(config)


class MevzuatTuruInferenceTests(unittest.TestCase):
    def test_2646_fixture_is_classified_as_yonetmelik(self):
        """2646 sayılı belge KANUN_ADI alanında "Kanun" hiç geçmiyor, ama
        gerçekte bir Yönetmelik — bu kritik ayrımı doğrular."""
        fixtures = {f.kanun_no: f for f in load_fixtures()}
        raw_doc = fixtures["2646"]
        self.assertIn("Yönetmelik", raw_doc.kanun_adi)
        doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
        self.assertEqual(doc.mevzuat_turu, "yönetmelik")

    def test_3071_fixture_defaults_to_kanun(self):
        fixtures = {f.kanun_no: f for f in load_fixtures()}
        raw_doc = fixtures["3071"]
        doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
        self.assertEqual(doc.mevzuat_turu, "kanun")

    def test_khk_detected_even_though_title_contains_kanun_word(self):
        turu = _infer_mevzuat_turu("Bazı Kanun Hükmünde Kararnamelerde Değişiklik Yapılmasına Dair KHK")
        self.assertEqual(turu, "khk")

    def test_teblig_detected(self):
        self.assertEqual(_infer_mevzuat_turu("Vergi Usul Kanunu Genel Tebliği"), "tebliğ")

    def test_anayasa_detected(self):
        self.assertEqual(_infer_mevzuat_turu("Türkiye Cumhuriyeti Anayasası"), "anayasa")

    def test_chunker_propagates_mevzuat_turu_to_metadata(self):
        text = "MADDE 1- Test metni."
        doc = parse_legislation_text(text, "9001", "Test Yönetmeliği", "https://example.test")
        chunks = StructureAwareChunker(max_tokens=768).chunk(doc)
        self.assertTrue(chunks)
        self.assertTrue(all(c.metadata.mevzuat_turu == "yönetmelik" for c in chunks))


class ContainsTableHeuristicTests(unittest.TestCase):
    def test_pipe_table_line_flagged(self):
        self.assertTrue(_looks_like_table_line("Sınıf | Ücret | Süre"))

    def test_aligned_columns_flagged(self):
        self.assertTrue(_looks_like_table_line("Sınıf A     10 TL     5 gün"))

    def test_repeated_numeric_unit_groups_flagged(self):
        self.assertTrue(_looks_like_table_line("10 kg 5 adet 3 gün"))

    def test_normal_prose_not_flagged(self):
        self.assertFalse(_looks_like_table_line("Bu maddenin amacı düzenlemektir ve gerekli şartları belirler."))

    def test_single_measurement_in_prose_not_flagged(self):
        """Tek bir ölçü ifadesi (örn. gerçek 2646 fixture'ındaki "210x297 mm")
        yanlış pozitif üretmemeli — heuristik en az 2 ardışık sayı+birim
        grubu arıyor."""
        self.assertFalse(
            _looks_like_table_line(
                "Belgelerin A4 (210x297 mm) boyutundaki kâğıda çıktı alınacak şekilde hazırlanması esastır."
            )
        )

    def test_real_fixtures_do_not_false_positive(self):
        """Gerçek corpus'ta tablo örneği yok — bu testin amacı heuristiğin
        gerçek metinde yanlış pozitif üretmediğini doğrulamak."""
        for raw_doc in load_fixtures():
            doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
            self.assertTrue(
                all(not m.contains_table for m in doc.maddeler),
                f"{raw_doc.kanun_no} içinde beklenmeyen contains_table=True",
            )

    def test_chunker_propagates_contains_table_to_metadata(self):
        text = "MADDE 1- (1) Sınıf A     10 TL     5 gün\n\nMADDE 2- (1) Normal düz metin burada."
        doc = parse_legislation_text(text, "9002", "Test Kanunu", "https://example.test")
        chunks = StructureAwareChunker(max_tokens=768).chunk(doc)

        by_madde = {c.metadata.madde_no: c for c in chunks}
        self.assertTrue(by_madde[1].metadata.contains_table)
        self.assertFalse(by_madde[2].metadata.contains_table)


class GenerationContextWarningTests(unittest.TestCase):
    def test_hierarchy_note_present_in_system_prompt(self):
        self.assertIn("Anayasa", SYSTEM_PROMPT)
        self.assertIn("Kanun", SYSTEM_PROMPT)
        self.assertIn("KHK", SYSTEM_PROMPT)
        self.assertIn("Yönetmelik", SYSTEM_PROMPT)
        self.assertIn("Tebliğ", SYSTEM_PROMPT)

    def test_context_warns_on_contains_table(self):
        table_chunk = LegislationChunk(
            id="c1", text="Sınıf A     10 TL     5 gün",
            metadata=ChunkMetadata(
                kanun_no="1111", kanun_adi="Test", madde_no=1, fikra_no=None, bent=None,
                kaynak_url="", source_hash="x", contains_table=True,
            ),
            citation="1111 sayılı Test, Madde 1",
        )
        normal_chunk = LegislationChunk(
            id="c2", text="Başka bir madde metni.",
            metadata=ChunkMetadata(
                kanun_no="1111", kanun_adi="Test", madde_no=2, fikra_no=None, bent=None,
                kaynak_url="", source_hash="y", contains_table=False,
            ),
            citation="1111 sayılı Test, Madde 2",
        )
        context = _build_context([
            RetrievalResult(chunk=table_chunk, score=0.9),
            RetrievalResult(chunk=normal_chunk, score=0.8),
        ])

        self.assertIn("[⚠️ TABLO/EK OLABİLİR] Sınıf A     10 TL     5 gün", context)
        self.assertNotIn("⚠️", context.split("[2]")[1])  # ikinci kaynakta uyarı yok


class RealQdrantRoundTripTests(unittest.TestCase):
    """Kritik test: mevzuat_turu ve contains_table yalnızca bellek-içi
    nesnelerde değil, gerçek Qdrant'a upsert edilip GERİ OKUNDUKTAN sonra da
    korunmalı. store.py'nin upsert_chunks/search'ünün yeni alanları
    payload'a yazmayı/okumayı unutması (durum alanı için daha önce yaşanmış
    bir bug, bkz. models.py) burada fark edilmeden kalamaz."""

    def test_mevzuat_turu_and_contains_table_survive_real_qdrant_round_trip(self):
        # semantik retrieval (engine.retrieve()) burada KASITLI olarak
        # kullanılmıyor: hangi maddenin top-k'ya girip min_score eşiğini
        # geçeceği embedding/rerank gürültüsüne bağlı olabilir (ilk sürümde
        # "tablo" sorgusu bu yüzden flaky bir KeyError'a yol açmıştı). Bu
        # test yalnızca "alanlar Qdrant'a yazılıp geri okunurken korunuyor
        # mu?" sorusuna cevap arıyor, retrieval kalitesine değil — bu yüzden
        # store.scroll_all_chunks() ile TÜM chunk'lar deterministik olarak
        # okunuyor.
        text = (
            "MADDE 1- (1) Sınıf A     10 TL     5 gün\n\n"
            "MADDE 2- (1) Normal yürürlükteki madde metni burada."
        )
        doc = parse_legislation_text(text, "9999", "Test Yönetmeliği", "https://example.test")
        self.assertEqual(doc.mevzuat_turu, "yönetmelik")
        chunks = StructureAwareChunker(max_tokens=768).chunk(doc)

        with tempfile.TemporaryDirectory() as tmp:
            engine = _fresh_engine("hierarchy_table_roundtrip_test", tmp)
            engine.index_chunks(chunks)

            all_chunks = engine.store.scroll_all_chunks()
            by_madde = {c.metadata.madde_no: c.metadata for c in all_chunks}

            self.assertEqual(by_madde[1].mevzuat_turu, "yönetmelik")
            self.assertTrue(by_madde[1].contains_table)

            self.assertEqual(by_madde[2].mevzuat_turu, "yönetmelik")
            self.assertFalse(by_madde[2].contains_table)


if __name__ == "__main__":
    unittest.main()
