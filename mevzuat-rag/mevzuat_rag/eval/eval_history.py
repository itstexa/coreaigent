"""Retrieval eval sonuçları için kalıcı geçmiş kaydı.

docs/IMPROVEMENT_IDEAS.md'deki "Gözlemlenebilirlik #4 — Drift/regresyon
paneli" fikrinin uygulamasıdır: ``run_retrieval_eval.run(engine)``
``{"per_case": [...], "summary": {...}}`` döndürüyor ama hiçbir yere kalıcı
yazılmıyor — süreç bitince sonuç kayboluyor, dolayısıyla Recall@K / MRR /
latency'nin zaman içindeki trendini (iyileşiyor mu, geriliyor mu / bir
değişiklik regresyona mı yol açtı) görmenin bir yolu yoktu.

``ingest_pipeline.py``'nin çalıştırma kayıtlarını ``logs/`` altına yazan
deseniyle aynı fikir: append-only bir kayıt dosyası, her koşu bir satır.
``per_case`` (tek tek sorgu) detayı BİLEREK yazılmıyor — yalnızca
``summary`` (Recall@K, MRR, latency_ms_p50/max, n_queries, ...) + zaman
damgası. Her golden-set sorgusunun tüm ayrıntısını her koşuda biriktirmek
dosyayı hızla şişirir; trend takibi için gereken tek şey özet metrikleridir,
tek tek sorgu satırları değil.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

# mevzuat_rag/eval/eval_history.py -> parent=eval/, parent.parent=mevzuat_rag/,
# parent.parent.parent = proje kökü (mevzuat-rag/) -> mevzuat-rag/logs/
HISTORY_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "eval_history.jsonl"
_lock = threading.Lock()


def append_history(result: dict, history_path: Path | None = None) -> None:
    """``result`` (``run_retrieval_eval.run()``'ın döndürdüğü sözlük) içindeki
    ``summary`` kısmını, zaman damgasıyla birlikte ``logs/eval_history.jsonl``'a
    tek bir satır olarak ekler. ``per_case`` detayı yazılmaz.

    Append-only — asla üzerine yazmaz, asla mevcut satırları silmez/değiştirmez.
    """
    path = history_path or HISTORY_PATH
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": result.get("summary", {}),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_history(history_path: Path | None = None) -> list[dict]:
    """``logs/eval_history.jsonl``'daki kayıtları dosyadaki sırayla (en
    eskiden en yeniye) bir liste olarak döner. Dosya yoksa/boşsa boş liste
    döner — çağıran taraf "hiç geçmiş yok" durumunu ayrıca ele almak
    zorunda kalmasın diye."""
    path = history_path or HISTORY_PATH
    if not path.exists():
        return []

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
