"""Yürürlük durumu (mülga/değişik) takibi testleri.

sample_data/legislation/ içindeki 2 gerçek belgede "(Mülga: ...)" / "(Değişik:
...)" kalıbının hiç örneği yok (corpus çok küçük/temiz) — bu yüzden testler
resmi mevzuat kaynaklarının (mevzuat.gov.tr) standart notasyonunu taklit eden
sentetik metinlerle yazıldı, dürüstçe not edilmiştir.
"""
from __future__ import annotations

from mevzuat_rag.chunking.chunker import StructureAwareChunker
from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text
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
