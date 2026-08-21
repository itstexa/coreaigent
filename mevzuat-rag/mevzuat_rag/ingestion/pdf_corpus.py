"""PDF corpus loader — tasarım hedefi: ~1.000.000 PDF'lik bir dizini,
belleğe hepsini yüklemeden, kesintiden sonra kaldığı yerden devam ederek,
ve PII hiçbir zaman chunk/embedding/LLM sınırını geçmeden işleyebilmek.

Üç tasarım kararı, tam bu yüzden:

1. **Akış (streaming), liste değil.** ``iter_pdf_paths`` bir generator —
   ``Path.rglob`` zaten tembel, 1M dosya yolu asla aynı anda bellekte
   değil. ``load_pdf_corpus`` de bir generator — ``ingest_pipeline.run()``
   zaten dokümanları teker teker işliyor (bkz. ``load_fixtures``'ın yerini
   alması), o yüzden burada da hiçbir noktada tüm korpus RAM'e girmiyor.

2. **Checkpoint = devam edebilirlik.** 1M dosyalık bir koşu kesintiye
   uğrayacaktır (OOM, kapatma, hata) — sıfırdan başlamak günler kaybettirir.
   Checkpoint dosyası (JSONL) her işlenen yolu + ucuz bir parmak izi
   (boyut+mtime, tüm dosyayı yeniden okuyup hash'lemek 1M ölçekte pahalı)
   kaydeder; bir sonraki koşu değişmemiş dosyaları atlar.

3. **PII, worker'da, chunk'lanmadan önce redakte edilir.** Her worker
   process kendi PDF'ini okur → metni çıkarır → ``redact_pii`` uygular →
   yalnızca redakte edilmiş metni ana sürece döndürür. Ham (redakte
   edilmemiş) metin worker process'in dışına asla çıkmaz.

Kapsam dışı: taranmış/görüntü PDF'ler (OCR gerektirir, bu modülün işi
değil — bkz. coreaigent'ın ayrı ``ocr`` servisi), gerçek bir dağıtık kuyruk
(Celery/Kafka) — ``multiprocessing.Pool`` tek makinede yeterli, 1M dosyanın
birden fazla makineye dağıtılması ayrı bir ileri adım.
"""
from __future__ import annotations

import json
import logging
import multiprocessing
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from mevzuat_rag.ingestion.base import RawDocument
from mevzuat_rag.ingestion.normalize import normalize_whitespace
from mevzuat_rag.pii import redact_pii

logger = logging.getLogger(__name__)


@dataclass
class PdfIngestStats:
    seen: int = 0
    skipped_unchanged: int = 0
    extracted: int = 0
    failed: int = 0
    pii_redactions: int = 0


def iter_pdf_paths(root: Path) -> Iterator[Path]:
    """rglob tembel bir generator'dür — 1M dosyada bile tüm liste RAM'e girmez."""
    yield from root.rglob("*.pdf")


def _fingerprint(path: Path) -> str:
    """Tüm dosyayı hash'lemek yerine ucuz bir parmak izi: boyut+mtime.
    1M dosyada her birini baştan sona okumak (yalnızca 'değişti mi?' sorusu
    için) darboğaz olur; bu, o maliyeti kabul edilebilir bir hata payıyla
    (aynı saniyede aynı boyutta üzerine yazma gibi nadir durumlar) ortadan
    kaldırır."""
    stat = path.stat()
    return f"{stat.st_size}:{int(stat.st_mtime)}"


def _load_checkpoint(checkpoint_path: Path) -> dict[str, str]:
    if not checkpoint_path.exists():
        return {}
    done: dict[str, str] = {}
    with checkpoint_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("status") == "ok":
                done[row["path"]] = row["fingerprint"]
    return done


def _append_checkpoint(checkpoint_path: Path, row: dict) -> None:
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        # Parolasız açmayı dene (bazı PDF'ler boş parolayla "encrypted" işaretli).
        reader.decrypt("")
    parts = [page.extract_text() or "" for page in reader.pages]
    return normalize_whitespace("\n".join(parts))


def _process_one(path_str: str) -> dict:
    """Worker process'te çalışır: PDF -> metin -> PII redaksiyonu.
    Ham metin bu fonksiyonun dışına asla çıkmaz — yalnızca redakte edilmiş
    metin ve sayaçlar ana sürece dönüyor."""
    path = Path(path_str)
    try:
        raw_text = extract_pdf_text(path)
    except (PdfReadError, OSError, ValueError) as exc:
        return {"path": path_str, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    if not raw_text.strip():
        return {"path": path_str, "status": "failed", "error": "boş/çıkarılamayan metin (taranmış görüntü olabilir)"}

    redaction = redact_pii(raw_text)
    return {
        "path": path_str,
        "status": "ok",
        "fingerprint": _fingerprint(path),
        "text": redaction.text,
        "pii_counts": redaction.counts,
    }


def load_pdf_corpus(
    root: Path,
    checkpoint_path: Path,
    workers: int = 4,
    chunksize: int = 8,
) -> Iterator[RawDocument]:
    """1M-ölçekli PDF dizinini gezip her belge için redakte edilmiş bir
    ``RawDocument`` üretir. ``ingest_pipeline.run()`` bunu ``load_fixtures()``
    ile aynı şekilde ``for raw_doc in ...:`` ile tüketir — akış tek
    değişmeden kalır, sadece kaynak değişir."""
    done = _load_checkpoint(checkpoint_path)
    stats = PdfIngestStats()

    def _pending() -> Iterator[str]:
        for path in iter_pdf_paths(root):
            stats.seen += 1
            path_str = str(path)
            fp = _fingerprint(path)
            if done.get(path_str) == fp:
                stats.skipped_unchanged += 1
                continue
            yield path_str

    # "spawn", "fork" değil: ana süreç embedding modelini (PyTorch/CUDA) zaten
    # yüklemiş ve çoklu thread'li olabilir — CUDA sonrası fork() bilinen bir
    # kilitlenme/çökme kaynağıdır. Worker'lar zaten torch import etmiyor, o
    # yüzden spawn'ın küçük başlatma maliyeti (yeniden import) tercih edildi.
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(processes=workers) as pool:
        for result in pool.imap_unordered(_process_one, _pending(), chunksize=chunksize):
            if result["status"] != "ok":
                stats.failed += 1
                _append_checkpoint(checkpoint_path, {"path": result["path"], "status": "failed", "error": result["error"]})
                logger.warning("PDF atlandı (%s): %s", result["path"], result["error"])
                continue

            stats.extracted += 1
            stats.pii_redactions += sum(result["pii_counts"].values())
            _append_checkpoint(
                checkpoint_path,
                {"path": result["path"], "status": "ok", "fingerprint": result["fingerprint"]},
            )
            if result["pii_counts"]:
                logger.info("PII redakte edildi (%s): %s", result["path"], result["pii_counts"])

            stem = Path(result["path"]).stem
            yield RawDocument(
                kanun_no=stem,
                kanun_adi=stem,
                url=f"file://{result['path']}",
                raw_text=result["text"],
            )

    logger.info(
        "PDF korpus taraması bitti — görülen: %d, atlanan (değişmemiş): %d, "
        "çıkarılan: %d, başarısız: %d, redakte edilen PII alanı: %d",
        stats.seen, stats.skipped_unchanged, stats.extracted, stats.failed, stats.pii_redactions,
    )
