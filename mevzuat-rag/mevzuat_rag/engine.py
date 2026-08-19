"""RAG engine facade: retrieve() for plain retrieval, ask() for a grounded
DeepSeek-generated answer over the retrieved chunks. Both run a Pipeline of
Stages (see pipeline/) — see the README's "Pipeline" section for the stage
list and which ones are wired up so far.

This is the standalone-package version — no HTTP contract coupling (that
lived in coreaigent's services/rag/server.py). Import RAGEngine and call
retrieve()/ask() directly, or use ask.py's CLI.
"""
from __future__ import annotations

import threading

from mevzuat_rag import metrics
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.embedding import embed_texts_with_config, get_embedder
from mevzuat_rag.errors import RAGError
from mevzuat_rag.models import LegislationChunk, RetrievalResult
from mevzuat_rag.pipeline.bm25_index import BM25Index
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.pipeline.runner import Pipeline
from mevzuat_rag.pipeline.stages.compression import CompressionStage
from mevzuat_rag.pipeline.stages.crag import CRAGStage
from mevzuat_rag.pipeline.stages.generate import GenerateStage
from mevzuat_rag.pipeline.stages.hybrid_retrieve import HybridRetrieveStage
from mevzuat_rag.pipeline.stages.hyde import HyDEStage
from mevzuat_rag.pipeline.stages.multi_query import MultiQueryStage
from mevzuat_rag.pipeline.stages.parent_doc import ParentDocStage
from mevzuat_rag.pipeline.stages.rerank import RerankStage
from mevzuat_rag.pipeline.stages.router import RouterStage
from mevzuat_rag.store import QdrantStore
from mevzuat_rag.text_norm import TEXT_NORM_VERSION

__all__ = ["RAGEngine", "RAGError"]


class RAGEngine:
    def __init__(self, config: RAGConfig | None = None):
        self.config = config or RAGConfig.from_env()
        self._store: QdrantStore | None = None
        self._model = None
        self._store_lock = threading.Lock()
        self._model_lock = threading.Lock()
        self.bm25_index = BM25Index()

    @property
    def store(self) -> QdrantStore:
        # [1] Multi-Query/HyDE's dense searches run from a thread pool
        # (see hybrid_retrieve.py) — without this lock, concurrent
        # first-access threads race to construct the embedded Qdrant
        # client and collide on its on-disk lock file.
        if self._store is None:
            with self._store_lock:
                if self._store is None:
                    self._store = QdrantStore(
                        collection=self.config.qdrant_collection,
                        url=self.config.qdrant_url,
                        local_path=self.config.qdrant_local_path,
                        embedding_model=self.config.embedding_model,
                        embedding_dim=self.config.embedding_dim,
                        text_norm_version=TEXT_NORM_VERSION if self.config.text_norm.version_check else None,
                    )
        return self._store

    @property
    def model(self):
        if self._model is None:
            with self._model_lock:
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

    def index_chunks(self, chunks: list[LegislationChunk]) -> dict:
        """Embeds and upserts ``chunks``, skipping ones whose content hasn't
        changed since the last run (same chunk id + same ``source_hash``).

        This is what makes "drop a new/edited .md file and re-run
        ingest_pipeline" cheap: unrelated, already-indexed files are not
        re-embedded just because the pipeline ran again.

        Batch-level embedding failures no longer abort the whole ingest. Failed
        chunks are isolated and reported in ``failed`` so later CLI/ingest code
        can persist them without losing the successfully embedded chunks.
        """
        if not chunks:
            return {"embedded": 0, "skipped_unchanged": 0, "failed": []}

        existing = self.store.existing_source_hashes([chunk.id for chunk in chunks])
        to_embed = [chunk for chunk in chunks if existing.get(chunk.id) != chunk.metadata.source_hash]
        skipped = len(chunks) - len(to_embed)
        failed: list[dict] = []
        embedded = 0

        if to_embed:
            batch_size = max(1, self.config.embedding.batch_size)

            for i in range(0, len(to_embed), batch_size):
                batch = to_embed[i:i + batch_size]

                with metrics.timer("embedding_batch", input_count=len(batch)) as t:
                    try:
                        vectors = embed_texts_with_config(
                            self.model,
                            [chunk.text for chunk in batch],
                            config=self.config.embedding,
                        )
                        self.store.upsert_chunks(batch, vectors)
                        embedded += len(batch)
                        t.output_count = len(batch)
                    except Exception:
                        # Bu batch kalıcı olarak başarısız olduysa tüm ingest'i
                        # düşürme; her chunk'ı tek tek dene ve sadece gerçekten
                        # sorunlu olanları failed listesine al. Bu iç hata
                        # metrics.timer() tarafından status="ok" olarak
                        # kaydedilir çünkü izole edilip burada tüketildi —
                        # dışarı sızan tek şey failed[] listesindeki kayıtlar.
                        batch_failed = 0
                        for chunk in batch:
                            try:
                                vectors = embed_texts_with_config(
                                    self.model,
                                    [chunk.text],
                                    config=self.config.embedding,
                                )
                                self.store.upsert_chunks([chunk], vectors)
                                embedded += 1
                            except Exception as chunk_exc:
                                failed.append({"chunk_id": chunk.id, "error": str(chunk_exc)})
                                batch_failed += 1
                        t.output_count = len(batch) - batch_failed

            if embedded:
                self.bm25_index.invalidate()

        return {"embedded": embedded, "skipped_unchanged": skipped, "failed": failed}

    def _build_pipeline(self, want_answer: bool) -> Pipeline:
        stages = [
            RouterStage(enabled=self.config.router.enabled),
            MultiQueryStage(enabled=self.config.multi_query.enabled),
            HyDEStage(enabled=self.config.hyde.enabled),
            HybridRetrieveStage(enabled=True),
            RerankStage(enabled=self.config.rerank.enabled),
            ParentDocStage(enabled=self.config.parent_doc.enabled),
            CRAGStage(enabled=self.config.crag.enabled),
            CompressionStage(enabled=self.config.compression.enabled),
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
        """retrieve() + DeepSeek-generated grounded answer. See generation.py.

        If ``config.debug`` (or ``RAG_DEBUG=true``) is set, the returned
        dict also carries a ``"trace"`` list — one entry per stage that
        actually ran, with its input/output candidate count and duration in
        ms (see pipeline/context.py:TraceEntry) — so you can see which
        stages fired and what each one changed for this specific query.
        """
        if not query:
            raise RAGError("query is required", category="validation")
        top_k = top_k or self.config.retrieval_top_k
        ctx = self._run(query, top_k, want_answer=True)
        answer = ctx.answer
        if self.config.debug:
            answer["trace"] = [
                {"stage": t.stage, "input_count": t.input_count, "output_count": t.output_count, "duration_ms": t.duration_ms}
                for t in ctx.trace
            ]
        return answer
