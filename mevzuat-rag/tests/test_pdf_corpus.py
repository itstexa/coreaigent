"""PDF korpus loader testleri — uçtan uca gerçek PDF dosyalarıyla (sentetik,
uydurma içerikli). PyMuPDF (fitz) yalnızca test fixture'ı üretmek için
kullanılıyor; üretim/runtime kodu (pdf_corpus.py) her sayfayı pdfplumber ile
işliyor (tablo yapısını korumak için — bkz. pdf_corpus.py'deki
"Tablo-farkında çıkarım: performans stratejisi" notu ve
tests/test_table_aware_pdf.py), pypdf ise yalnızca şifre çözme kontrolü ve
pdfplumber'ın tamamen başarısız olduğu nadir durumda geri dönüş yolu için
kullanılıyor.

TCKN test sabiti (11111111110) checksum algoritmasını geçen sentetik bir
numaradır, gerçek bir kişiye ait değildir (bkz. test_pii.py).
"""
from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz", reason="PyMuPDF yalnızca test fixture PDF üretimi için gerekli, runtime bağımlılığı değil")

from mevzuat_rag.ingestion.pdf_corpus import load_pdf_corpus


def _make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text, fontsize=10)
    doc.save(str(path))
    doc.close()


@pytest.fixture
def pdf_dir(tmp_path: Path) -> Path:
    root = tmp_path / "pdfs"
    root.mkdir()
    _make_pdf(
        root / "with_pii.pdf",
        "Basvuru sahibinin TCKN: 11111111110 Tel: 05321234567\nMADDE 1- Bu bir test maddesidir.",
    )
    _make_pdf(root / "plain.pdf", "MADDE 1- Kisisel veri icermeyen bir belge.")
    (root / "corrupt.pdf").write_bytes(b"this is not a real pdf file")
    return root


def test_pii_redacted_before_leaving_worker(pdf_dir: Path, tmp_path: Path):
    checkpoint = tmp_path / "checkpoint.jsonl"
    docs = {d.kanun_no: d for d in load_pdf_corpus(pdf_dir, checkpoint, workers=2)}

    assert "with_pii" in docs
    assert "11111111110" not in docs["with_pii"].raw_text
    assert "05321234567" not in docs["with_pii"].raw_text
    assert "[TCKN]" in docs["with_pii"].raw_text
    assert "[TELEFON]" in docs["with_pii"].raw_text


def test_corrupt_pdf_does_not_crash_batch(pdf_dir: Path, tmp_path: Path):
    checkpoint = tmp_path / "checkpoint.jsonl"
    docs = list(load_pdf_corpus(pdf_dir, checkpoint, workers=2))

    # 3 dosyadan 2'si gerçek PDF (corrupt.pdf başarısız olmalı, diğer ikisi geçmeli)
    assert len(docs) == 2
    checkpoint_lines = checkpoint.read_text(encoding="utf-8").splitlines()
    statuses = [line for line in checkpoint_lines]
    assert any('"status": "failed"' in line and "corrupt.pdf" in line for line in statuses)


def test_checkpoint_skips_unchanged_files_on_second_run(pdf_dir: Path, tmp_path: Path):
    checkpoint = tmp_path / "checkpoint.jsonl"

    first_run = list(load_pdf_corpus(pdf_dir, checkpoint, workers=2))
    assert len(first_run) == 2  # with_pii.pdf + plain.pdf (corrupt.pdf başarısız)

    second_run = list(load_pdf_corpus(pdf_dir, checkpoint, workers=2))
    assert second_run == []  # hiçbir şey değişmedi, hepsi atlanmalı


def test_new_file_after_checkpoint_is_picked_up(pdf_dir: Path, tmp_path: Path):
    checkpoint = tmp_path / "checkpoint.jsonl"
    list(load_pdf_corpus(pdf_dir, checkpoint, workers=2))

    _make_pdf(pdf_dir / "yeni_belge.pdf", "MADDE 1- Sonradan eklenen belge.")
    second_run = list(load_pdf_corpus(pdf_dir, checkpoint, workers=2))

    assert len(second_run) == 1
    assert second_run[0].kanun_no == "yeni_belge"
