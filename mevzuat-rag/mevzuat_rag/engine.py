"""RAG engine facade: retrieve() for plain retrieval, ask() for a grounded
DeepSeek-generated answer over the retrieved chunks. Both run a Pipeline of
Stages (see pipeline/) — see the README's "Pipeline" section for the stage
list and which ones are wired up so far.

This is the standalone-package version — no HTTP contract coupling (that
lived in coreaigent's services/rag/server.py). Import RAGEngine and call
retrieve()/ask() directly, or use ask.py's CLI.
"""
from __future__ import annotations

from mevzuat_rag.config import RAGConfig
from mevzuat_rag.embedding import embed_texts, get_embedder
from mevzuat_rag.errors import RAGError
from mevzuat_rag.models import LegislationChunk, RetrievalResult
from mevzuat_rag.pipeline.bm25_index import BM25Index
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.pipeline.runner import Pipeline
from mevzuat_rag.pipeline.stages.generate import GenerateStage
from mevzuat_rag.pipeline.stages.hybrid_retrieve import HybridRetrieveStage
from mevzuat_rag.pipeline.stages.rerank import RerankStage
from mevzuat_rag.store import QdrantStore

__all__ = ["RAGEngine", "RAGError"]


class RAGEngine:
    def __init__(self, config: RAGConfig | None = None):
        self.config = config or RAGConfig.from_env()
        self._store: QdrantStore | None = None
        self._model = None
        self.bm25_index = BM25Index()

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
            self.bm25_index.invalidate()

        return {"embedded": len(to_embed), "skipped_unchanged": skipped}

    def _build_pipeline(self, want_answer: bool) -> Pipeline:
        stages = [
            HybridRetrieveStage(enabled=True),
            RerankStage(enabled=self.config.rerank.enabled),
        ]
        if want_answer:
            stages.append(GenerateStage(enabled=True))
        return Pipeline(stages)

    def _run(self, query: str, top_k: int, want_answer: bool) -> PipelineContext:
        ctx = PipelineContext(original_query=query, engine=self, top_k=top_k, debug=self.config.debug)
        pipeline = self._build_pipeline(want_answer=want_answer)
        return pipeline.run(ctx)

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievalResult]:
        if not query:
            raise RAGError("query is required", category="validation")
        top_k = top_k or self.config.retrieval_top_k
        ctx = self._run(query, top_k, want_answer=False)
        return [candidate.to_result() for candidate in ctx.candidates]

    def ask(self, query: str, top_k: int | None = None) -> dict:
        """retrieve() + DeepSeek-generated grounded answer. See generation.py."""
        if not query:
            raise RAGError("query is required", category="validation")
        top_k = top_k or self.config.retrieval_top_k
        ctx = self._run(query, top_k, want_answer=True)
        return ctx.answer
