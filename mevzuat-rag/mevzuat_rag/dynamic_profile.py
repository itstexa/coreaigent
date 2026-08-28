"""[Dinamik RAG ve VRAM Optimizasyon Yönergesi] Sorgu geldiğinde hedef
korpusun (Qdrant koleksiyonunun) toplam chunk sayısına bakılır ve KÜÇÜK /
ORTA / BÜYÜK profillerinden biri seçilir — her profil Multi-Query/HyDE/
hibrit-arama-k/rerank-aday-sayısı/parent-doc/CRAG için farklı bir VRAM ↔
gecikme dengesi kurar (2026-08-28, gerçek 4090 ölçümü sonrası eklendi —
bkz. docs/PERFORMANCE_REPORT_4090_240pg.md: tek sorguda 47-91 aday
reranker'a gidiyordu, bu profil onu 10-15'e sabitler).

KRİTİK: bu modül ``RAGEngine.config``'i ASLA mutate etmez — yalnızca
``dataclasses.replace`` ile İSTEĞE ÖZEL yeni bir ``RAGConfig`` üretip
döndürür. Aksi halde aynı ``RAGEngine``'i paylaşan eşzamanlı istekler
(çoklu kullanıcı) birbirinin profilini ezerdi — crag.py'deki "Deliberately
does NOT mutate ctx.engine.config" uyarısıyla aynı disiplin.

Sınırlar CHUNK sayısına göredir (sayfa değil) — gerçek VRAM/gecikme maliyeti
(embed_query varyant sayısı, rerank'e giden aday sayısı, CRAG döngüsü)
doğrudan chunk sayısıyla orantılı, sayfa sayısıyla değil:
  KÜÇÜK   : < 1000 chunk   (~0-50 sayfa)
  ORTA    : 1000-5000 chunk (~50-250 sayfa)
  BÜYÜK   : > 5000 chunk    (~250+ sayfa)
"""
from __future__ import annotations

import dataclasses

from mevzuat_rag.config import RAGConfig

SMALL_MAX_CHUNKS = 1000
MEDIUM_MAX_CHUNKS = 5000

# Belirsiz/ambiguous soru tespiti için HyDE eşiği (ORTA profil) — direktif
# "15 kelimeden kısaysa" diyor, kelime sayımı burada yapılır (mevcut
# hyde.py'nin kendi token-tabanlı trigger_max_tokens eşiğinden BAĞIMSIZ —
# bu profil enabled/disabled'ı doğrudan karara bağlıyor, hyde.py'nin içindeki
# tetikleyici tekrar devreye girmesin diye HyDEStage zaten enabled=False
# ise hiç çalışmıyor).
MEDIUM_HYDE_MAX_WORDS = 15


def resolve_profile_name(point_count: int) -> str:
    if point_count < SMALL_MAX_CHUNKS:
        return "small"
    if point_count <= MEDIUM_MAX_CHUNKS:
        return "medium"
    return "large"


def _word_count(text: str) -> int:
    return len(text.split())


def apply_dynamic_profile(base: RAGConfig, point_count: int, query: str) -> tuple[RAGConfig, str]:
    """``base``'i mutate etmeden, bu TEK istek için geçerli yeni bir
    RAGConfig + seçilen profil adını döndürür."""
    profile_name = resolve_profile_name(point_count)

    if profile_name == "small":
        # KÜÇÜK BELGE & YÜKSEK TRAFİK MODU — VRAM maksimum düzeyde korunur.
        effective = dataclasses.replace(
            base,
            multi_query=dataclasses.replace(base.multi_query, enabled=False),
            hyde=dataclasses.replace(base.hyde, enabled=False),
            hybrid=dataclasses.replace(base.hybrid, rrf_k=10),
            rerank=dataclasses.replace(base.rerank, max_candidates=10, top_n=3),
            parent_doc=dataclasses.replace(base.parent_doc, enabled=False),
            crag=dataclasses.replace(base.crag, max_loops=1),
        )
    elif profile_name == "medium":
        # ORTA BELGE & DENGELİ MOD — hafif bağlam desteği.
        hyde_enabled = base.hyde.enabled and _word_count(query) < MEDIUM_HYDE_MAX_WORDS
        effective = dataclasses.replace(
            base,
            multi_query=dataclasses.replace(base.multi_query, enabled=base.multi_query.enabled, n_queries=1),
            hyde=dataclasses.replace(base.hyde, enabled=hyde_enabled),
            hybrid=dataclasses.replace(base.hybrid, rrf_k=20),
            rerank=dataclasses.replace(base.rerank, max_candidates=15, top_n=4),
            parent_doc=dataclasses.replace(
                base.parent_doc, enabled=base.parent_doc.enabled, token_budget_fraction=0.4
            ),
            crag=dataclasses.replace(base.crag),
        )
    else:
        # BÜYÜK KORPUS / MEVZUAT & DERİN ARAMA MODU.
        effective = dataclasses.replace(
            base,
            multi_query=dataclasses.replace(base.multi_query, enabled=base.multi_query.enabled, n_queries=2),
            hyde=dataclasses.replace(base.hyde, enabled=base.hyde.enabled),
            hybrid=dataclasses.replace(base.hybrid, rrf_k=30),
            rerank=dataclasses.replace(base.rerank, max_candidates=15, top_n=5),
            parent_doc=dataclasses.replace(
                base.parent_doc, enabled=base.parent_doc.enabled, token_budget_fraction=0.6
            ),
            crag=dataclasses.replace(base.crag),
        )

    return effective, profile_name
