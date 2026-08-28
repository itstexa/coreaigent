"""BM25 (sparse) tarafı artık Qdrant'ın kendi native sparse index'inde
yaşıyor (bkz. store.py:search_sparse, pipeline/sparse_vector.py) — bu sınıf
geriye dönük uyumluluk için aynı ``.search(query, top_k, store)`` arayüzünü
koruyan ince bir sarmalayıcı (hybrid_retrieve.py ve crag.py'nin
``shift_to_bm25`` stratejisi bunu çağırıyor).

ESKİ TASARIM (artık geçerli değil): ``store.scroll_all_chunks()`` ile tüm
korpusu belleğe çekip ``rank_bm25.BM25Okapi`` ile yeniden kuruyordu — kendi
docstring'i "a few thousand chunks at most" diyordu, bu da paketin
1M-dosya PDF ingestion hedefiyle (bkz. ingestion/pdf_corpus.py) doğrudan
çelişiyordu (denetim bulgusu, rag_config_panel.py madde 4). Artık her
chunk'ın sparse vektörü upsert anında Qdrant'a yazılıyor (store.py:
upsert_chunks), index disk-backed/kalıcı ve korpus boyutundan bağımsız
sabit bellek kullanıyor — ``invalidate()`` bu yüzden artık no-op: senkron
tutulacak ayrı bir in-memory kopya kalmadı.
"""
from __future__ import annotations

from mevzuat_rag.models import LegislationChunk
from mevzuat_rag.store import QdrantStore


class BM25Index:
    def invalidate(self) -> None:
        """No-op — bkz. modül docstring'i. Çağrı yerleri (engine.py) için
        geriye dönük uyumluluk amacıyla korunuyor."""
        return

    def search(self, query: str, top_k: int, store: QdrantStore) -> list[tuple[LegislationChunk, float]]:
        results = store.search_sparse(query, top_k=top_k)
        return [(r.chunk, float(r.score)) for r in results]
