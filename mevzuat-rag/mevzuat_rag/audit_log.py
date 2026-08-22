"""[Güvenlik] Audit log — kim/ne zaman/ne sordu/hangi maddeler döndü kaydı.

Kamu evrak sistemlerinde hesap verebilirlik ve olası bir PII sızıntısı
sonrası adli inceleme için zorunlu bir iz — 2026-08-22 alt-ajan taramasında
bulunan boşluk (bkz. docs/IMPROVEMENT_IDEAS.md, Güvenlik #2): kod tabanında
hiçbir audit/access-log modülü yoktu.

Append-only JSONL, ingest_pipeline.py'nin logs/ dosyalarıyla aynı desende.
Ham chunk METNİ değil, yalnızca citation'lar (madde numaraları) loglanır —
audit log'un kendisi ayrı bir PII-taşıyan yüzey olmasın diye.

``actor=None``: bu sistemde henüz kimlik doğrulama/kullanıcı kavramı yok
(bkz. IMPROVEMENT_IDEAS.md Güvenlik #3, "kullanıcı bazlı yetkilendirme" ayrı
bir gelecek iş) — ``actor`` alanı ileride bir auth katmanı eklendiğinde
doldurulmak üzere şimdiden şemada var.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "audit.jsonl"
_lock = threading.Lock()


def log_query(
    query: str,
    citations: list[str],
    answer_verdict: str | None = None,
    actor: str | None = None,
    log_path: Path | None = None,
) -> None:
    """Append-only — asla üzerine yazmaz, asla silmez."""
    path = log_path or LOG_PATH
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "query": query,
        "citations": citations,
        "answer_verdict": answer_verdict,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
