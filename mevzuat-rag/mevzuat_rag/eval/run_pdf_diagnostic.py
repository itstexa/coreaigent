"""PDF-ingest doğruluk testi — offline_docs/*.txt altındaki gerçek mevzuat
metinlerini gerçekçi, çok sayfalı PDF'lere render eder, GERÇEK PDF ingest
yolundan (``ingestion/pdf_corpus.load_pdf_corpus`` — pypdf ile metin
çıkarımı + PII redaksiyonu, sentetik test fixture'ı değil) geçirip ayrı,
geçici bir Qdrant koleksiyonuna indexler, sonra golden_set.jsonl'daki
o kanunlara ait sorularla test eder.

Sorulan soru: ".md/.txt fixture'lardan üretilen mevcut prod index ile
AYNI metin gerçek bir PDF'ten geçirildiğinde retrieval kalitesi (doğru
kanun_no + madde_no bulma — yani 'konum') korunuyor mu?"

Prod koleksiyonuna (mevzuat_chunks) DOKUNMAZ — ayrı `pdf_diagnostic_test`
koleksiyonu, ayrı geçici dizin, script sonunda silinir.

    python -m mevzuat_rag.eval.run_pdf_diagnostic
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

import fitz  # PyMuPDF — yalnızca bu teşhis scriptinin PDF üretimi için, runtime bağımlılığı değil

from mevzuat_rag import ingest_pipeline
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.eval.retrieval_metrics import mrr, precision_at_k, recall_at_k
from mevzuat_rag.ingestion.pdf_corpus import load_pdf_corpus

OFFLINE_DOCS_DIR = Path(__file__).resolve().parents[2] / "sample_data" / "legislation" / "offline_docs"
GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.jsonl"
K_VALUES = (1, 3, 5)


def _madde_key(kanun_no: str, madde_no) -> str:
    return f"{kanun_no}:{madde_no}"


@lru_cache(maxsize=1)
def _unicode_font_path() -> str:
    """Base-14 fontlar (helv/Helvetica) WinAnsiEncoding kullanır ve
    İ/ı/Ğ/ş gibi Türkçe'ye özgü karakterleri desteklemez (render sırasında
    '?' olur) — gerçek mevzuat PDF'leri gömülü Unicode fontlar kullandığı
    için bu test de öyle yapmalı, aksi halde PII/madde tespiti gerçekçi
    olmayan bozuk metin üzerinde ölçülür. fc-match ile sistemdeki DejaVu
    Sans'ı (tam Latin Extended-A kapsamı) bulur — sabit kodlu bir path
    yerine, farklı ortamlarda kırılmaması için."""
    out = subprocess.run(
        ["fc-match", "-f", "%{file}", "DejaVu Sans"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not out or not Path(out).exists():
        raise RuntimeError("DejaVu Sans fontu bulunamadı (fc-match) — Türkçe karakterler doğru render edilemez")
    return out


def _render_pdf(text: str, out_path: Path) -> int:
    """Metni gerçekçi, çok sayfalı, kelime-sınırında bölünmüş bir PDF'e
    render eder (tek insert_text çağrısıyla değil — insert_textbox gerçek
    bir taranmamış PDF'in üreteceği satır/sayfa akışına daha yakın).
    Türkçe karakterler (İ ı Ğ Ş ç ö ü) Unicode font ile korunur. Sayfa
    sayısını döndürür.

    insert_textbox'ın taşan metni kaç karakterde kestiğini garanti veren
    bir API yok, bu yüzden kelime sınırında bir bütçeyle böler: sığmazsa
    (rc < 0) bütçeyi yarıya indirip tekrar dener."""
    font_path = _unicode_font_path()
    doc = fitz.open()
    rect = fitz.Rect(50, 50, 545, 792)
    words = text.split(" ")
    pages = 0
    i = 0
    budget = 220  # kelime/sayfa, ilk tahmin
    while i < len(words):
        n = min(budget, len(words) - i)
        while n > 1:
            chunk = " ".join(words[i : i + n])
            page = doc.new_page(width=595, height=842)
            page.insert_font(fontname="DejaVu", fontfile=font_path)
            rc = page.insert_textbox(rect, chunk, fontsize=10, fontname="DejaVu", align=0)
            if rc >= 0:
                break
            doc.delete_page(page.number)
            n = max(1, n // 2)
        else:
            chunk = " ".join(words[i : i + n])
            page = doc.new_page(width=595, height=842)
            page.insert_font(fontname="DejaVu", fontfile=font_path)
            page.insert_textbox(rect, chunk, fontsize=10, fontname="DejaVu", align=0)
        i += n
        pages += 1
    doc.save(str(out_path))
    doc.close()
    return pages


def _count_madde(text: str) -> int:
    # IGNORECASE: bazı kanun metinleri "MADDE 1-" yerine "Madde 1 -" gibi
    # karışık büyük/küçük harf kullanır (ör. 4721 Türk Medeni Kanunu) —
    # aynı esneklik mevzuat_rag/chunking/legal_structure_parser.py'deki
    # üretim regex'inde de var (MADDE_RE, re.IGNORECASE).
    return len(re.findall(r"(?im)^\s*MADDE\s+\d+", text))


def run() -> dict:
    metadata = json.loads((OFFLINE_DOCS_DIR / "metadata.json").read_text(encoding="utf-8"))
    golden_cases = [json.loads(line) for line in GOLDEN_SET_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]

    pdf_kanun_nos = {entry["kanun_no"] for entry in metadata.values()}
    cases = [
        c for c in golden_cases
        if not c.get("must_refuse") and all(e["kanun_no"] in pdf_kanun_nos for e in c["expected"])
    ]

    tmp_root = Path(tempfile.mkdtemp(prefix="pdf_diagnostic_"))
    pdf_dir = tmp_root / "pdfs"
    pdf_dir.mkdir()
    checkpoint = tmp_root / "checkpoint.jsonl"

    render_report = []
    try:
        for txt_name, entry in metadata.items():
            src_text = (OFFLINE_DOCS_DIR / txt_name).read_text(encoding="utf-8")
            madde_count_source = _count_madde(src_text)
            # NOT: load_pdf_corpus() kanun_no'yu PDF içeriğinden değil dosya
            # adından (stem) türetiyor (bkz. ingestion/pdf_corpus.py) — bu
            # yüzden burada dosyayı kasıtlı olarak "{kanun_no}.pdf" adıyla
            # yazıyoruz (üretimde PDF'lerin kanun numarasıyla adlandırıldığı
            # iyimser senaryo). Orijinal dosya adı (ör. bir betik/tarama
            # ismi) kullanılsaydı retrieve() madde_no'yu yine doğru bulur
            # ama kanun_no yanlış/anlamsız çıkardı — bkz. rapordaki
            # "PDF kanun_no kaynağı" bulgusu.
            pdf_path = pdf_dir / (entry["kanun_no"] + ".pdf")
            n_pages = _render_pdf(src_text, pdf_path)
            render_report.append({
                "kanun_no": entry["kanun_no"],
                "kanun_adi": entry["kanun_adi"],
                "source_file": txt_name,
                "source_chars": len(src_text),
                "madde_count_source_txt": madde_count_source,
                "pdf_pages_rendered": n_pages,
            })

        config = RAGConfig.from_env()
        config.qdrant_local_path = str(tmp_root / "qdrant")
        config.qdrant_collection = "pdf_diagnostic_test"
        engine = RAGEngine(config)

        docs = list(load_pdf_corpus(pdf_dir, checkpoint, workers=1))
        doc_by_kanun = {d.kanun_no: d for d in docs}

        # extract_pdf_text (pypdf) ile çıkarılan metindeki MADDE sayısını
        # kaynak .txt'deki ile karşılaştır — pypdf'in PDF'ten metin
        # çıkarırken madde başlıklarını kaybedip kaybetmediğini gösterir.
        for row in render_report:
            extracted = doc_by_kanun.get(row["kanun_no"])
            row["pdf_extracted"] = extracted is not None
            if extracted:
                row["madde_count_extracted_from_pdf"] = _count_madde(extracted.raw_text)
                row["madde_count_match"] = row["madde_count_extracted_from_pdf"] == row["madde_count_source_txt"]

        summary_ingest = ingest_pipeline.run(engine, documents=docs, flush_every=0)

        per_case = []
        for case in cases:
            relevant = {_madde_key(e["kanun_no"], e["madde_no"]) for e in case["expected"]}
            hits = engine.retrieve(case["query"], top_k=max(K_VALUES), actor="eval:run_pdf_diagnostic")
            retrieved = [_madde_key(hit.chunk.metadata.kanun_no, hit.chunk.metadata.madde_no) for hit in hits]
            row = {"query": case["query"], "expected": sorted(relevant), "top1_got": retrieved[0] if retrieved else None}
            for k in K_VALUES:
                row[f"recall@{k}"] = round(recall_at_k(retrieved, relevant, k), 3)
                row[f"precision@{k}"] = round(precision_at_k(retrieved, relevant, k), 3)
            row["mrr"] = round(mrr(retrieved, relevant), 3)
            per_case.append(row)

        n = len(per_case)
        summary_retrieval = {}
        if n:
            summary_retrieval.update({f"recall@{k}": round(sum(r[f"recall@{k}"] for r in per_case) / n, 3) for k in K_VALUES})
            summary_retrieval.update({f"precision@{k}": round(sum(r[f"precision@{k}"] for r in per_case) / n, 3) for k in K_VALUES})
            summary_retrieval["mrr"] = round(sum(r["mrr"] for r in per_case) / n, 3)
        summary_retrieval["n_queries"] = n

        return {
            "render_report": render_report,
            "ingest_summary": {
                "documents": summary_ingest.get("documents"),
                "chunks": summary_ingest.get("totals", {}).get("embedded", 0) + summary_ingest.get("totals", {}).get("skipped_unchanged", 0),
                "embedded": summary_ingest.get("totals", {}).get("embedded"),
                "failed": summary_ingest.get("totals", {}).get("failed"),
            },
            "per_case": per_case,
            "summary_retrieval": summary_retrieval,
        }
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    result = run()
    print("=== PDF render + ekstraksiyon raporu ===")
    for row in result["render_report"]:
        print(row)
    print()
    print("=== Ingest özeti ===")
    print(result["ingest_summary"])
    print()
    print("=== Sorgu bazlı sonuçlar (PDF'ten indexlenen corpus üzerinde) ===")
    for row in result["per_case"]:
        print(row)
    print()
    print("=== Özet (PDF corpus retrieval) ===")
    print(result["summary_retrieval"])
