"""In-memory BM25 sparse index sharing the same chunk_id space as the dense
Qdrant store (spec: "Vector DB native desteklemiyorsa ayrı bir BM25 index'i
tut... aynı chunk_id uzayını paylaşsın"). Qdrant has no native BM25, so this
rebuilds a ``rank_bm25.BM25Okapi`` index from the current contents of the
Qdrant collection (via ``store.scroll_all_chunks``) — cheap enough for a
legislation corpus (a few thousand chunks at most), no separate persistence
needed. ``RAGEngine.index_chunks`` invalidates it whenever new/changed
chunks are embedded, so the next hybrid retrieve rebuilds it lazily.
"""
from __future__ import annotations

from rank_bm25 import BM25Okapi

from mevzuat_rag.models import LegislationChunk
from mevzuat_rag.pipeline.tokenize_tr import tokenize
from mevzuat_rag.store import QdrantStore


class BM25Index:
    def __init__(self):
        self._bm25: BM25Okapi | None = None
        self._chunks: list[LegislationChunk] = []

    def invalidate(self) -> None:
        self._bm25 = None
        self._chunks = []

    def _ensure_built(self, store: QdrantStore) -> None:
        if self._bm25 is not None:
            return
        self._chunks = store.scroll_all_chunks()
        tokenized = [tokenize(chunk.text) for chunk in self._chunks]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def search(self, query: str, top_k: int, store: QdrantStore) -> list[tuple[LegislationChunk, float]]:
        self._ensure_built(store)
        if self._bm25 is None or not self._chunks:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self._chunks, scores), key=lambda pair: pair[1], reverse=True)
        return [(chunk, float(score)) for chunk, score in ranked[:top_k] if score > 0]
