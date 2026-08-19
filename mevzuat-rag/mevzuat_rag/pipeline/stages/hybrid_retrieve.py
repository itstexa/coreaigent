"""[2] Hybrid Retrieve — dense (vector) search always; sparse (BM25) search
+ RRF/weighted fusion when ``config.hybrid.enabled``. When hybrid is
disabled this reproduces exactly the pre-pipeline dense-only retrieve()
behavior (same top_k, same store.search call) — nothing here changes for
callers that never touch hybrid.enabled.

Embeds ``ctx.hyde_answer`` instead of the raw query when HyDE has set it
(checkpoint 3) — no change needed here when that stage is added.

When hybrid is enabled, this stage does NOT truncate to ctx.top_k — it
leaves up to ``max(dense_top_k, bm25_top_k)`` fused candidates for
[3] Rerank to narrow down. If reranking is disabled, it truncates to
ctx.top_k itself so ungraded, oversized candidate sets never reach
[7] Generate.
"""
from __future__ import annotations

from mevzuat_rag.embedding import embed_query
from mevzuat_rag.errors import RAGError
from mevzuat_rag.models import LegislationChunk, RetrievalResult
from mevzuat_rag.pipeline.candidate import Candidate
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.pipeline.fusion import reciprocal_rank_fusion, weighted_fusion


class HybridRetrieveStage:
    name = "hybrid_retrieve"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        engine = ctx.engine
        hybrid = engine.config.hybrid
        query_text = ctx.hyde_answer or ctx.original_query

        try:
            query_vector = embed_query(engine.model, query_text)
        except Exception as exc:
            raise RAGError(f"embedding failed: {exc}", category="dependency") from exc

        dense_top_k = hybrid.dense_top_k if hybrid.enabled else ctx.top_k
        try:
            dense_hits = engine.store.search(query_vector, top_k=dense_top_k)
        except Exception as exc:
            raise RAGError(f"retrieval failed: {exc}", category="dependency") from exc

        if not hybrid.enabled:
            ctx.candidates = [Candidate.from_result(hit, source="dense") for hit in dense_hits]
            return ctx

        try:
            bm25_hits = engine.bm25_index.search(query_text, top_k=hybrid.bm25_top_k, store=engine.store)
        except Exception as exc:
            raise RAGError(f"bm25 retrieval failed: {exc}", category="dependency") from exc

        chunks_by_id: dict[str, LegislationChunk] = {hit.chunk.id: hit.chunk for hit in dense_hits}
        dense_scores: dict[str, float] = {hit.chunk.id: hit.score for hit in dense_hits}
        bm25_scores: dict[str, float] = {}
        for chunk, score in bm25_hits:
            chunks_by_id.setdefault(chunk.id, chunk)
            bm25_scores[chunk.id] = score

        if hybrid.fusion == "weighted":
            fused = weighted_fusion(dense_scores, bm25_scores, alpha=hybrid.alpha)
        else:
            dense_ranked_ids = [hit.chunk.id for hit in dense_hits]
            bm25_ranked_ids = [chunk.id for chunk, _ in bm25_hits]
            fused = reciprocal_rank_fusion([dense_ranked_ids, bm25_ranked_ids], k=hybrid.rrf_k)

        ranked_ids = sorted(fused, key=lambda chunk_id: fused[chunk_id], reverse=True)
        candidates = []
        for chunk_id in ranked_ids:
            chunk = chunks_by_id[chunk_id]
            candidate = Candidate.from_result(RetrievalResult(chunk=chunk, score=fused[chunk_id]), source="fused")
            candidate.metadata["dense_score"] = dense_scores.get(chunk_id)
            candidate.metadata["bm25_score"] = bm25_scores.get(chunk_id)
            candidates.append(candidate)

        if not engine.config.rerank.enabled:
            candidates = candidates[: ctx.top_k]
        ctx.candidates = candidates
        return ctx
