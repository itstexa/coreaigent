"""RAG engine facade: retrieve() for plain retrieval, ask() for a grounded
DeepSeek-generated answer over the retrieved chunks.

This is the standalone-package version — no HTTP contract coupling (that
lived in coreaigent's services/rag/server.py). Import RAGEngine and call
retrieve()/ask() directly, or use ask.py's CLI.
"""
from __future__ import annotations

from mevzuat_rag import generation
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.embedding import embed_query, embed_texts, get_embedder
from mevzuat_rag.models import LegislationChunk, RetrievalResult
from mevzuat_rag.store import QdrantStore


class RAGError(Exception):
    def __init__(self, message: str, category: str = "validation"):
        super().__init__(message)
        self.category = category


class RAGEngine:
    def __init__(self, config: RAGConfig | None = None):
        self.config = config or RAGConfig.from_env()
        self._store: QdrantStore | None = None
        self._model = None

    @property
    def store(self) -> QdrantStore:
        if self._store is None:
            self._store = QdrantStore(
                collection=self.config.qdrant_collection,
                url=self.config.qdrant_url,
                local_path=self.config.qdrant_local_path,
            )
        return self._store

    @property
    def model(self):
        if self._model is None:
            self._model = get_embedder(self.config.embedding_model, self.config.embedding_device)
        return self._model

    def is_ready(self) -> bool:
        try:
            _ = self.model
            _ = self.store.client.get_collections()
            return True
        except Exception:
            return False

    def index_chunks(self, chunks: list[LegislationChunk]) -> dict[str, int]:
        """Embeds and upserts ``chunks``, skipping ones whose content hasn't
        changed since the last run (same chunk id + same ``source_hash``).

        This is what makes "drop a new/edited .md file and re-run
        ingest_pipeline" cheap: unrelated, already-indexed files are not
        re-embedded just because the pipeline ran again.
        """
        if not chunks:
            return {"embedded": 0, "skipped_unchanged": 0}

        existing = self.store.existing_source_hashes([chunk.id for chunk in chunks])
        to_embed = [chunk for chunk in chunks if existing.get(chunk.id) != chunk.metadata.source_hash]
        skipped = len(chunks) - len(to_embed)

        if to_embed:
            vectors = embed_texts(self.model, [chunk.text for chunk in to_embed])
            self.store.upsert_chunks(to_embed, vectors)

        return {"embedded": len(to_embed), "skipped_unchanged": skipped}

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        if not query:
            raise RAGError("query is required", category="validation")
        top_k = top_k or self.config.retrieval_top_k
        try:
            query_vector = embed_query(self.model, query)
        except Exception as exc:
            raise RAGError(f"embedding failed: {exc}", category="dependency") from exc
        try:
            return self.store.search(query_vector, top_k=top_k)
        except Exception as exc:
            raise RAGError(f"retrieval failed: {exc}", category="dependency") from exc

    def ask(self, query: str, top_k: int | None = None) -> dict:
        """retrieve() + DeepSeek-generated grounded answer. See generation.py."""
        hits = self.retrieve(query, top_k=top_k)
        result = generation.generate_answer(query, hits)
        result["sources"] = [
            {"citation": hit.chunk.citation, "score": round(float(hit.score), 3), "text": hit.chunk.text}
            for hit in hits
        ]
        return result
