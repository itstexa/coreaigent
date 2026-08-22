"""Yürürlük durumu (mülga/değişik) takibi testleri.

sample_data/legislation/ içindeki 2 gerçek belgede "(Mülga: ...)" / "(Değişik:
...)" kalıbının hiç örneği yok (corpus çok küçük/temiz) — bu yüzden testler
resmi mevzuat kaynaklarının (mevzuat.gov.tr) standart notasyonunu taklit eden
sentetik metinlerle yazıldı, dürüstçe not edilmiştir.
"""
from __future__ import annotations

import tempfile

from mevzuat_rag.chunking.chunker import StructureAwareChunker
from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.generation import _build_context
from mevzuat_rag.models import RetrievalResult


def test_mulga_madde_detected():
    text = "MADDE 9- (Mülga: 12/7/2013-6495/77 md.)"
    doc = parse_legislation_text(text, "1111", "Test Kanunu", "https://example.com")
    assert doc.maddeler[0].durum == "mülga"


def test_degisik_madde_detected_and_text_preserved():
    text = "MADDE 5- (Değişik: 10/6/2020-7245/12 md.) Yeni madde metni burada devam eder."
    doc = parse_legislation_text(text, "1111", "Test Kanunu", "https://example.com")
    madde = doc.maddeler[0]
    assert madde.durum == "değişik"
    # Değişiklik notundan sonraki gerçek metin kaybolmamalı.
    assert "Yeni madde metni burada devam eder" in madde.fikralar[0].text


def test_normal_madde_defaults_to_yururlukte():
    text = "MADDE 1- Bu kanunun amacı şudur."
    doc = parse_legislation_text(text, "1111", "Test Kanunu", "https://example.com")
    assert doc.maddeler[0].durum == "yürürlükte"


def test_mulga_uppercase_and_no_parenthesis_variants():
    for line in ["MADDE 3- MÜLGA", "MADDE 3- Mülga:", "MADDE 3- (mülga)"]:
        doc = parse_legislation_text(line, "1111", "Test Kanunu", "https://example.com")
        assert doc.maddeler[0].durum == "mülga", line


def test_chunker_propagates_durum_to_metadata():
    text = "MADDE 9- (Mülga: 12/7/2013-6495/77 md.)\n\nMADDE 10- Normal yürürlükteki madde metni."
    doc = parse_legislation_text(text, "1111", "Test Kanunu", "https://example.com")
    chunks = StructureAwareChunker(max_tokens=768).chunk(doc)

    by_madde = {c.metadata.madde_no: c for c in chunks}
    assert by_madde[9].metadata.durum == "mülga"
    assert by_madde[10].metadata.durum == "yürürlükte"


def test_chunker_propagates_durum_for_long_fikra_path():
    """Bir fıkra max_tokens'ı aşınca chunker'ın AYRI (flush()'tan farklı)
    ChunkMetadata inşa yolu çalışır — o yol da durum'u miras almalı."""
    uzun_metin = "kelime " * 2000  # max_tokens'ı zorlamak için
    text = f"MADDE 7- (Mülga: 1/1/2020-1234/5 md.)\n(1) {uzun_metin}"
    doc = parse_legislation_text(text, "1111", "Test Kanunu", "https://example.com")
    chunks = StructureAwareChunker(max_tokens=50).chunk(doc)
    assert len(chunks) >= 1
    assert all(c.metadata.durum == "mülga" for c in chunks)


def test_generation_context_warns_on_mulga():
    from mevzuat_rag.models import ChunkMetadata, LegislationChunk

    mulga_chunk = LegislationChunk(
        id="c1", text="Bu madde metni.",
        metadata=ChunkMetadata(kanun_no="1111", kanun_adi="Test", madde_no=9, fikra_no=None, bent=None,
                                kaynak_url="", source_hash="x", durum="mülga"),
        citation="1111 sayılı Test, Madde 9",
    )
    normal_chunk = LegislationChunk(
        id="c2", text="Başka bir madde metni.",
        metadata=ChunkMetadata(kanun_no="1111", kanun_adi="Test", madde_no=10, fikra_no=None, bent=None,
                                kaynak_url="", source_hash="y", durum="yürürlükte"),
        citation="1111 sayılı Test, Madde 10",
    )
    context = _build_context([RetrievalResult(chunk=mulga_chunk, score=0.9), RetrievalResult(chunk=normal_chunk, score=0.8)])

    assert "[⚠️ MÜLGA — YÜRÜRLÜKTE DEĞİL] Bu madde metni." in context
    assert "[⚠️" not in context.split("[2]")[1]  # ikinci kaynakta uyarı yok


def test_durum_survives_real_qdrant_round_trip():
    """Kritik test: durum yalnızca bellek-içi nesnelerde değil, gerçek
    Qdrant'a upsert edilip GERİ OKUNDUKTAN sonra da korunmalı. Bu test
    olmadan store.py'nin upsert_chunks/scroll_all_chunks/search/
    get_chunks_by_madde'sinin 'durum'u payload'a hiç yazmadığı/okumadığı
    (her zaman varsayılana "yürürlükte" düşürdüğü) bir bug fark edilmeden
    kalabilirdi — tam da bu testi yazarken bulundu ve store.py'de düzeltildi."""
    text = (
        "MADDE 1- (Mülga: 1/1/2020-1234/5 md.)\n\n"
        "MADDE 2- Yürürlükteki normal madde metni burada."
    )
    doc = parse_legislation_text(text, "9999", "Test Kanunu", "https://example.com")
    chunks = StructureAwareChunker(max_tokens=768).chunk(doc)

    with tempfile.TemporaryDirectory() as tmp:
        config = RAGConfig.from_env()
        config.qdrant_local_path = tmp
        config.qdrant_collection = "durum_roundtrip_test"
        engine = RAGEngine(config)

        engine.index_chunks(chunks)

        # 1) get_chunks_by_madde üzerinden (parent_doc/citation_expansion'ın kullandığı yol)
        madde1_chunks = engine.store.get_chunks_by_madde("9999", 1)
        assert madde1_chunks[0].metadata.durum == "mülga"
        madde2_chunks = engine.store.get_chunks_by_madde("9999", 2)
        assert madde2_chunks[0].metadata.durum == "yürürlükte"

        # 2) scroll_all_chunks üzerinden (BM25 index'in kullandığı yol)
        all_chunks = engine.store.scroll_all_chunks()
        by_madde = {c.metadata.madde_no: c for c in all_chunks}
        assert by_madde[1].metadata.durum == "mülga"
        assert by_madde[2].metadata.durum == "yürürlükte"

        # 3) search() üzerinden (asıl sorgu/retrieve() yolu)
        hits = engine.retrieve("mülga madde", top_k=5)
        mulga_hits = [h for h in hits if h.chunk.metadata.madde_no == 1]
        assert mulga_hits and mulga_hits[0].chunk.metadata.durum == "mülga"


def test_generation_context_warns_on_degisik():
    from mevzuat_rag.models import ChunkMetadata, LegislationChunk

    chunk = LegislationChunk(
        id="c1", text="Değişmiş madde metni.",
        metadata=ChunkMetadata(kanun_no="1111", kanun_adi="Test", madde_no=5, fikra_no=None, bent=None,
                                kaynak_url="", source_hash="x", durum="değişik"),
        citation="1111 sayılı Test, Madde 5",
    )
    context = _build_context([RetrievalResult(chunk=chunk, score=0.9)])
    assert "[⚠️ DEĞİŞİK] Değişmiş madde metni." in context
