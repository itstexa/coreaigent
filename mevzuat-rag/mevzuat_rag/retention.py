"""[5] Güvenlik — PII redaksiyonu sonrası veri saklama/silme politikası.

Uygulaması: docs/IMPROVEMENT_IDEAS.md, "3. Güvenlik, Gizlilik ve Uyumluluk"
bölümü, madde 5 — "Qdrant'ta TTL/silme mekanizması yok, KVKK'nın 'amaç sona
erince sil' ilkesi karşılanmıyor."

``store.py``'deki ``upsert_chunks`` artık her point'in payload'ına
``indexed_at`` (ISO-8601 UTC) yazıyor. Bu modül o alanı kullanarak yaşa göre
silme sağlar:

- ``list_retention_candidates`` — hiçbir şey silmeden, ``days`` günden eski
  chunk'ların dry-run listesini döner (kullanıcı gözden geçirsin diye).
- ``delete_older_than`` — aynı kriterle GERÇEKTEN siler.

Qdrant'ın filtre API'si tarih aralığını doğrudan destekleyebilir
(``DatetimeRange``), ama burada bilinçli olarak ``scroll`` + Python-tarafı
karşılaştırma tercih edildi: ``indexed_at`` düz bir string payload alanı
olarak yazılıyor (index'lenmiş bir datetime field değil), bu yüzden
sunucu-tarafı range filtresi ekstra bir payload index kurulumu gerektirir.
Küçük/orta ölçekli koleksiyonlarda scroll+Python filtresi hem daha basit hem
de ``store.py``'deki ``delete_by_kanun_no``'nun zaten kullandığı
``Filter``/``FieldCondition`` desenine ek bir bağımlılık getirmiyor.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mevzuat_rag.store import QdrantStore


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _parse_indexed_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _scroll_candidates(store: QdrantStore, days: int, batch_size: int = 256) -> list[dict]:
    """Tüm koleksiyonu tarar, ``indexed_at`` alanı ``days`` günden eski (veya
    hiç yazılmamış — eski/legacy point'ler için güvenli varsayılan: silinecek
    aday sayılır, çünkü ne zaman indekslendiği hiç bilinmiyor) olan
    point'lerin id/kanun_no/madde_no/indexed_at bilgisini döner."""
    cutoff = _cutoff(days)
    candidates: list[dict] = []
    offset = None
    while True:
        points, offset = store.client.scroll(
            collection_name=store.collection,
            limit=batch_size,
            offset=offset,
            with_payload=["kanun_no", "madde_no", "indexed_at"],
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            indexed_at_raw = payload.get("indexed_at")
            indexed_at = _parse_indexed_at(indexed_at_raw)
            # indexed_at eksikse (upsert_chunks bu alanı yazmadan önce
            # indekslenmiş eski/legacy point) ne zaman indekslendiği hiç
            # bilinmiyor demektir — KVKK açısından en riskli durum, o yüzden
            # saklama süresini aşmış kabul edilip silme adayına eklenir.
            if indexed_at is None or indexed_at < cutoff:
                candidates.append(
                    {
                        "id": str(point.id),
                        "kanun_no": payload.get("kanun_no"),
                        "madde_no": payload.get("madde_no"),
                        "indexed_at": indexed_at_raw,
                    }
                )
        if offset is None:
            break
    return candidates


def list_retention_candidates(store: QdrantStore, days: int) -> list[dict]:
    """``days`` günden eski (ya da ``indexed_at``'i hiç olmayan) chunk'ların
    dry-run listesi — hiçbir şey silmez. Her öğe: id, kanun_no, madde_no,
    indexed_at."""
    return _scroll_candidates(store, days)


def delete_older_than(store: QdrantStore, days: int) -> int:
    """``days`` günden eski TÜM chunk'ları siler, silinen sayıyı döner.

    ``scroll`` + Python-tarafı filtreyle adayları toplar, sonra id
    listesiyle ``client.delete`` çağırır (Qdrant id listesiyle silmeyi
    doğrudan destekler — ``store.py``'deki ``delete_by_kanun_no``'nun
    kullandığı ``Filter`` yerine burada doğrudan id listesi kullanılıyor,
    çünkü kriter tarih — Qdrant filtre API'sinde string ``indexed_at``
    üzerinden doğrudan range karşılaştırması güvenilir değil)."""
    candidates = _scroll_candidates(store, days)
    ids = [c["id"] for c in candidates]
    if not ids:
        return 0
    store.client.delete(collection_name=store.collection, points_selector=ids)
    return len(ids)
