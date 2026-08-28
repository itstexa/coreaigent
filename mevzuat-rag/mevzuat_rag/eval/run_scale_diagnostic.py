"""Büyük ölçek PDF-ingest testi — Türkiye'nin en fazla maddeye sahip kanunuyla
(6102 sayılı Türk Ticaret Kanunu, 1535 madde, resmî mevzuat.gov.tr metni)
ve gerekirse ek kanunlarla toplam ~1000 sayfaya tamamlanmış bir korpusla,
gerçek PDF ingest hattının (ingestion/pdf_corpus.py) kaynak/zaman sınırlarını
ölçer.

    python -m mevzuat_rag.eval.run_scale_diagnostic --text /path/to/6102.txt=6102 [--text ... ]

Her --text argümanı ``dosya_yolu=kanun_no`` biçiminde. Birden çok kanun
verilirse hepsi aynı geçici koleksiyona indexlenir (toplam sayfa sayısını
büyütmek için). Prod koleksiyonuna dokunmaz — ayrı geçici dizin, script
sonunda silinir. GOLDEN_CASES sabiti, indexlenen metinden gerçek maddeler
okunarak elle doğrulanmış sorulardır (uydurma değil).
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from mevzuat_rag import ingest_pipeline
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.eval.retrieval_metrics import mrr, precision_at_k, recall_at_k
from mevzuat_rag.eval.run_pdf_diagnostic import _render_pdf, _count_madde
from mevzuat_rag.ingestion.pdf_corpus import load_pdf_corpus

K_VALUES = (1, 3, 5)

# 6102 sayılı Türk Ticaret Kanunu'nun resmî metninden (mevzuat.gov.tr)
# elle doğrulanmış madde/soru çiftleri.
GOLDEN_CASES_6102 = [
    {"query": "Her tacirin ticaretine ait faaliyetlerinde nasıl hareket etmesi gerekir?", "kanun_no": "6102", "madde_no": 18},
    {"query": "Tacir ticari işletmesine ilişkin işlemleri ne ile yapmak zorundadır?", "kanun_no": "6102", "madde_no": 39},
    {"query": "Ticaret şirketleri kaç türdür ve hangileridir?", "kanun_no": "6102", "madde_no": 124},
    {"query": "Anonim şirket nedir?", "kanun_no": "6102", "madde_no": 329},
    {"query": "Halka açık olmayan anonim şirketlerde en az başlangıç sermayesi ne kadardır?", "kanun_no": "6102", "madde_no": 332},
    {"query": "Limited şirket nedir?", "kanun_no": "6102", "madde_no": 573},
    {"query": "Haksız rekabete ilişkin hükümlerin amacı nedir?", "kanun_no": "6102", "madde_no": 54},
    {"query": "Ticaret şirketlerinde ortaklar arasındaki davalarda hangi yargılama usulü uygulanır?", "kanun_no": "6102", "madde_no": 1521},
]

# 4721 sayılı Türk Medeni Kanunu'nun resmî metninden (mevzuat.gov.tr)
# elle doğrulanmış madde/soru çiftleri.
GOLDEN_CASES_4721 = [
    {"query": "Her insanın hak ehliyeti var mıdır?", "kanun_no": "4721", "madde_no": 8},
    {"query": "Kişilik ne zaman başlar ve ne zaman sona erer?", "kanun_no": "4721", "madde_no": 28},
    {"query": "Erkek veya kadın kaç yaşını doldurmadan evlenemez?", "kanun_no": "4721", "madde_no": 124},
    {"query": "Eşlerden biri zina ederse diğer eş ne yapabilir?", "kanun_no": "4721", "madde_no": 161},
    {"query": "Mirasbırakanın birinci derece mirasçıları kimlerdir?", "kanun_no": "4721", "madde_no": 495},
    {"query": "Bir şeye malik olan kimsenin yetkileri nelerdir?", "kanun_no": "4721", "madde_no": 683},
]

ALL_GOLDEN_CASES = GOLDEN_CASES_6102 + GOLDEN_CASES_4721


def _madde_key(kanun_no: str, madde_no) -> str:
    return f"{kanun_no}:{madde_no}"


def _gpu_mem_mb() -> str:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        used, free = out.split(", ")
        return f"used={used}MiB free={free}MiB"
    except Exception:
        return "n/a"


def run(text_specs: list[tuple[Path, str]]) -> dict:
    tmp_root = Path(tempfile.mkdtemp(prefix="scale_diagnostic_"))
    pdf_dir = tmp_root / "pdfs"
    pdf_dir.mkdir()
    checkpoint = tmp_root / "checkpoint.jsonl"

    render_report = []
    t_render_total = 0.0
    try:
        for src_path, kanun_no in text_specs:
            src_text = src_path.read_text(encoding="utf-8")
            madde_count_source = _count_madde(src_text)
            pdf_path = pdf_dir / f"{kanun_no}.pdf"
            t0 = time.perf_counter()
            n_pages = _render_pdf(src_text, pdf_path)
            render_ms = (time.perf_counter() - t0) * 1000
            t_render_total += render_ms
            render_report.append({
                "kanun_no": kanun_no,
                "source_file": src_path.name,
                "source_chars": len(src_text),
                "madde_count_source": madde_count_source,
                "pdf_pages_rendered": n_pages,
                "render_ms": round(render_ms, 0),
                "pdf_size_mb": round(pdf_path.stat().st_size / 1e6, 2),
            })

        total_pages = sum(r["pdf_pages_rendered"] for r in render_report)
        total_chars = sum(r["source_chars"] for r in render_report)

        config = RAGConfig.from_env()
        config.qdrant_local_path = str(tmp_root / "qdrant")
        config.qdrant_collection = "scale_diagnostic_test"

        gpu_before = _gpu_mem_mb()
        t0 = time.perf_counter()
        engine = RAGEngine(config)
        docs = list(load_pdf_corpus(pdf_dir, checkpoint, workers=1))
        extract_ms = (time.perf_counter() - t0) * 1000

        doc_by_kanun = {d.kanun_no: d for d in docs}
        for row in render_report:
            extracted = doc_by_kanun.get(row["kanun_no"])
            row["pdf_extracted"] = extracted is not None
            if extracted:
                row["madde_count_extracted_from_pdf"] = _count_madde(extracted.raw_text)
                row["madde_count_match"] = row["madde_count_extracted_from_pdf"] == row["madde_count_source"]

        t0 = time.perf_counter()
        summary_ingest = ingest_pipeline.run(engine, documents=docs, flush_every=0)
        ingest_ms = (time.perf_counter() - t0) * 1000
        gpu_after = _gpu_mem_mb()

        cases = [c for c in ALL_GOLDEN_CASES if c["kanun_no"] in doc_by_kanun]
        per_case = []
        retrieve_latencies = []
        for case in cases:
            relevant = {_madde_key(case["kanun_no"], case["madde_no"])}
            t0 = time.perf_counter()
            hits = engine.retrieve(case["query"], top_k=max(K_VALUES), actor="eval:run_scale_diagnostic")
            lat_ms = (time.perf_counter() - t0) * 1000
            retrieve_latencies.append(lat_ms)
            retrieved = [_madde_key(hit.chunk.metadata.kanun_no, hit.chunk.metadata.madde_no) for hit in hits]
            row = {"query": case["query"], "expected": _madde_key(case["kanun_no"], case["madde_no"]),
                   "top1_got": retrieved[0] if retrieved else None, "latency_ms": round(lat_ms, 0)}
            for k in K_VALUES:
                row[f"recall@{k}"] = round(recall_at_k(retrieved, relevant, k), 3)
                row[f"precision@{k}"] = round(precision_at_k(retrieved, relevant, k), 3)
            row["mrr"] = round(mrr(retrieved, relevant), 3)
            per_case.append(row)

        n = len(per_case)
        summary_retrieval = {}
        if n:
            summary_retrieval.update({f"recall@{k}": round(sum(r[f"recall@{k}"] for r in per_case) / n, 3) for k in K_VALUES})
            summary_retrieval["mrr"] = round(sum(r["mrr"] for r in per_case) / n, 3)
            summary_retrieval["latency_ms_avg"] = round(sum(retrieve_latencies) / n, 0)
            summary_retrieval["latency_ms_max"] = round(max(retrieve_latencies), 0)
        summary_retrieval["n_queries"] = n

        return {
            "render_report": render_report,
            "scale": {
                "total_pdf_pages": total_pages,
                "total_source_chars": total_chars,
                "total_documents": len(text_specs),
            },
            "timing": {
                "render_ms_total": round(t_render_total, 0),
                "pdf_extract_ms_total": round(extract_ms, 0),
                "ingest_ms_total": round(ingest_ms, 0),
                "chunks_produced": summary_ingest.get("totals", {}).get("embedded", 0),
            },
            "gpu": {"before": gpu_before, "after": gpu_after},
            "ingest_summary": {
                "documents": summary_ingest.get("documents"),
                "embedded": summary_ingest.get("totals", {}).get("embedded"),
                "failed": summary_ingest.get("totals", {}).get("failed"),
            },
            "per_case": per_case,
            "summary_retrieval": summary_retrieval,
        }
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", action="append", required=True, help="dosya_yolu=kanun_no")
    args = parser.parse_args()

    specs = []
    for spec in args.text:
        path_str, kanun_no = spec.rsplit("=", 1)
        specs.append((Path(path_str), kanun_no))

    result = run(specs)
    print("=== Ölçek ===")
    print(result["scale"])
    print()
    print("=== Render + ekstraksiyon raporu ===")
    for row in result["render_report"]:
        print(row)
    print()
    print("=== Zamanlama ===")
    print(result["timing"])
    print()
    print("=== GPU VRAM ===")
    print(result["gpu"])
    print()
    print("=== Ingest özeti ===")
    print(result["ingest_summary"])
    print()
    print("=== Sorgu bazlı sonuçlar ===")
    for row in result["per_case"]:
        print(row)
    print()
    print("=== Özet (retrieval) ===")
    print(result["summary_retrieval"])
