"""Tablo-yapısını-koruyan PDF çıkarımı testleri — gerçek bir ruled (çizgili)
tabloyla uçtan uca (sentetik, uydurma içerikli, gerçek kişi/kurum verisi
yok).

PyMuPDF (fitz), tıpkı test_pdf_corpus.py'de olduğu gibi, YALNIZCA test
fixture PDF'i üretmek için kullanılıyor — gerçek tablo çizgileri
(``page.draw_line``) çizerek pdfplumber'ın varsayılan "lines" tespit
stratejisinin gerçekten tetiklenmesini sağlıyoruz (yalnızca metin hizalaması
değil). Üretim/runtime kodu (pdf_corpus.py) pypdf + pdfplumber kullanıyor,
fitz'e hiç bağımlı değil.

Bu dosyanın odaklandığı üç somut risk (görev tanımındaki 3 doğrulama
maddesi):
  1) Gerçek tablo hücre değerleri çıkarılan metinde grep'lenebilir mi?
  2) Markdown ayırıcı satırı ("|---|---|") ya da harf+")" ile başlayan bir
     hücre ("a) ..."), legal_structure_parser.py'nin BENT_RE/FIKRA_RE'siyle
     yanlışlıkla eşleşip sahte bir Bent/Fıkra düğümü mü yaratıyor?
  3) Tam parse->chunk geçişinden sonra ChunkMetadata.contains_table
     gerçekten True mu oluyor?
"""
from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz", reason="PyMuPDF yalnızca test fixture PDF üretimi için gerekli, runtime bağımlılığı değil")

from mevzuat_rag.chunking.chunker import StructureAwareChunker
from mevzuat_rag.chunking.legal_structure_parser import (
    BENT_RE,
    FIKRA_RE,
    MADDE_RE,
    parse_legislation_text,
)
from mevzuat_rag.ingestion.pdf_corpus import extract_pdf_text, table_to_markdown

ONCESI_MARKER = "ONCESI_METIN_MARKER"
SONRASI_MARKER = "SONRASI_METIN_MARKER"
UCRET_TEMEL = "TABLOUCRETI9042TL"
UCRET_OZEL = "TABLOUCRETI3157TL"
SURE_TEMEL = "TABLOSURESI7GUN"
SURE_OZEL = "TABLOSURESI21GUN"


def _draw_ruled_table(
    page: "fitz.Page",
    x0: float,
    y0: float,
    col_widths: list[float],
    rows: list[list[str]],
    row_height: float = 20.0,
) -> float:
    """Gerçek çizgilerle (yalnızca hizalanmış metinle değil) bir tablo çizer,
    böylece pdfplumber'ın varsayılan çizgi-tabanlı tespiti gerçekten
    tetiklenir (bkz. dosya üstü not). ``y1`` (tablonun alt sınırı) döner."""
    n_rows = len(rows)
    n_cols = len(col_widths)
    x1 = x0 + sum(col_widths)
    y1 = y0 + row_height * n_rows

    for r in range(n_rows + 1):
        y = y0 + r * row_height
        page.draw_line((x0, y), (x1, y))
    xc = x0
    for c in range(n_cols + 1):
        page.draw_line((xc, y0), (xc, y1))
        if c < n_cols:
            xc += col_widths[c]

    xc = x0
    for c in range(n_cols):
        yc = y0
        for r in range(n_rows):
            page.insert_text((xc + 5, yc + 14), rows[r][c], fontsize=9)
            yc += row_height
        xc += col_widths[c]

    return y1


@pytest.fixture
def table_pdf(tmp_path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()

    page.insert_text((50, 72), "MADDE 1- Bu maddede asagidaki ucret tarifesi", fontsize=10)
    page.insert_text((50, 88), f"{ONCESI_MARKER} uygulanir.", fontsize=10)

    table_rows = [
        ["Sinif", "Ucret", "Sure"],
        ["a) Temel Basvuru", UCRET_TEMEL, SURE_TEMEL],
        ["b) Ozel Basvuru", UCRET_OZEL, SURE_OZEL],
    ]
    y1 = _draw_ruled_table(page, x0=50, y0=110, col_widths=[140, 130, 110], rows=table_rows)

    page.insert_text((50, y1 + 30), f"{SONRASI_MARKER} Bu tarife her yil guncellenir.", fontsize=10)
    page.insert_text((50, y1 + 60), "MADDE 2- (1) Bu maddede tablo yoktur, sadece duz metin bulunur.", fontsize=10)

    path = tmp_path / "tablolu_belge.pdf"
    doc.save(str(path))
    doc.close()
    return path


class TestTableCellExtraction:
    """Görev maddesi 1: gerçek tablo hücre değerleri hayatta kalıyor ve
    grep'lenebiliyor mu?"""

    def test_table_cell_values_survive_extraction(self, table_pdf: Path):
        text = extract_pdf_text(table_pdf)

        for needle in (UCRET_TEMEL, UCRET_OZEL, SURE_TEMEL, SURE_OZEL, "Sinif", "Ucret", "Sure"):
            assert needle in text, f"{needle!r} çıkarılan metinde bulunamadı:\n{text}"

    def test_extracted_text_contains_markdown_table_markers(self, table_pdf: Path):
        text = extract_pdf_text(table_pdf)
        assert "|" in text
        assert "---" in text

    def test_text_table_ordering_is_preserved(self, table_pdf: Path):
        """Tek sütunlu (tek bantlı) bu sayfada tam sıralama garanti
        edilebilir (bkz. pdf_corpus.py'deki _extract_page_with_tables
        docstring'i — çok sütunlu sayfalarda bu YAKLAŞIK'tır, burada
        DEĞİL): tablo öncesi metin, tablo, tablo sonrası metin bu sırada
        çıkmalı."""
        text = extract_pdf_text(table_pdf)

        pos_before = text.index(ONCESI_MARKER)
        pos_table = text.index(UCRET_TEMEL)
        pos_after = text.index(SONRASI_MARKER)

        assert pos_before < pos_table < pos_after


class TestBentFikraMisparse:
    """Görev maddesi 2 (en olası gerçek bug): Markdown ayırıcı/hücre
    satırları BENT_RE ya da FIKRA_RE ile yanlışlıkla eşleşiyor mu?"""

    def test_separator_row_does_not_match_bent_or_fikra_or_madde(self):
        rows = [["a", "b"], ["1", "2"]]
        md = table_to_markdown(rows)
        separator_line = md.splitlines()[1]
        assert separator_line.startswith("|---")
        assert BENT_RE.match(separator_line) is None
        assert FIKRA_RE.match(separator_line) is None
        assert MADDE_RE.match(separator_line) is None

    def test_cell_starting_with_letter_paren_does_not_match_bent_re(self):
        """Asıl risk: bir hücre "a) ..." ile başlıyorsa (görevde verilen
        tam örnek), satırın GERÇEK ilk karakteri "|" olduğu için BENT_RE
        tetiklenmemeli."""
        md_row = table_to_markdown([["Sinif", "Ucret"], ["a) Temel", "500 TL"]])
        data_line = md_row.splitlines()[2]
        assert data_line.startswith("| a) Temel")
        assert BENT_RE.match(data_line) is None
        assert FIKRA_RE.match(data_line) is None
        assert MADDE_RE.match(data_line) is None

    def test_every_line_of_extracted_table_text_is_bent_fikra_safe(self, table_pdf: Path):
        text = extract_pdf_text(table_pdf)
        for line in text.splitlines():
            if line.strip().startswith("|"):
                assert BENT_RE.match(line.strip()) is None, f"tablo satırı yanlışlıkla BENT_RE ile eşleşti: {line!r}"
                assert FIKRA_RE.match(line.strip()) is None, f"tablo satırı yanlışlıkla FIKRA_RE ile eşleşti: {line!r}"

    def test_parser_does_not_create_spurious_bent_nodes_from_table_rows(self, table_pdf: Path):
        """Uçtan uca: gerçek PDF'ten çıkan metni parse_legislation_text'e
        ver, Madde 1'deki hiçbir FikraNode'un tablo satırlarından
        ("a) Temel Basvuru" / "b) Ozel Basvuru") sahte bir bent
        üretmediğini doğrula — metinde gerçek bir "a)"/"b)" bent işareti
        (satır başında, "|" olmadan) hiç yok."""
        text = extract_pdf_text(table_pdf)
        doc = parse_legislation_text(text, "9101", "Test Tarife Yönetmeliği", "https://example.test")

        assert len(doc.maddeler) == 2
        madde1 = doc.maddeler[0]
        assert madde1.madde_no == 1
        bent_letters = [f.bent for f in madde1.fikralar if f.bent is not None]
        assert bent_letters == [], f"Madde 1'de tablo satırlarından sahte bent(ler) üretildi: {bent_letters}"


class TestContainsTableMetadata:
    """Görev maddesi 3: tam parse->chunk geçişinden sonra
    ChunkMetadata.contains_table gerçekten True oluyor mu?"""

    def test_contains_table_true_on_chunk_with_table_false_on_chunk_without(self, table_pdf: Path):
        text = extract_pdf_text(table_pdf)
        doc = parse_legislation_text(text, "9101", "Test Tarife Yönetmeliği", "https://example.test")
        chunks = StructureAwareChunker(max_tokens=768).chunk(doc)

        by_madde = {c.metadata.madde_no: c for c in chunks}
        assert by_madde[1].metadata.contains_table is True
        assert by_madde[2].metadata.contains_table is False


class TestPlainPdfNoTableArtifacts:
    """Tablosuz bir PDF'te (pdfplumber yine de her sayfayı işler — bkz.
    pdf_corpus.py'deki performans notu: ucuz bir ön-filtre bilerek
    denenip kaldırıldı, gerçek çizgili tabloları kaçırıyordu) çıktının
    Markdown tablo işaretleri İÇERMEDİĞİNİ doğrular."""

    def test_plain_pdf_has_no_markdown_table_artifacts(self, tmp_path: Path):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 72), "MADDE 1- Bu bir test maddesidir, tablo icermez.", fontsize=10)
        path = tmp_path / "duz_metin.pdf"
        doc.save(str(path))
        doc.close()

        text = extract_pdf_text(path)
        assert "|" not in text
        assert "MADDE 1" in text
