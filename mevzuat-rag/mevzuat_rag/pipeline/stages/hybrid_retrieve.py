"""[2] Hybrid Retrieve — dense (vector) search over every query variant
(the original query, plus [1] Multi-Query's N generated queries when it ran,
plus [1] HyDE's hypothetical-answer text when it triggered) run concurrently
via a thread pool (spec: "Tüm sorgular paralel koşsun"); sparse (BM25)
search on the original query, added into the same fusion when
``config.hybrid.enabled``. All ranked lists are merged via RRF (default) or
weighted score fusion, keyed by chunk_id.

When hybrid is disabled AND neither multi-query nor HyDE produced anything
(the single-variant case), this reproduces exactly the pre-pipeline
dense-only retrieve() behavior (one embed call, one store.search call) —
nothing changes for callers that never touch hybrid/multi_query/hyde.

When hybrid is enabled, this stage does NOT truncate to ctx.top_k — it
leaves the fused candidate set for [3] Rerank to narrow down. If reranking
is disabled, it truncates to ctx.top_k itself so an oversized, ungraded
candidate set never reaches [7] Generate.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from mevzuat_rag.embedding import embed_query, embed_texts
from mevzuat_rag.errors import RAGError
from mevzuat_rag.models import LegislationChunk, RetrievalResult
from mevzuat_rag.pipeline.candidate import Candidate
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.pipeline.fusion import reciprocal_rank_fusion, weighted_fusion


def _query_variants(ctx: PipelineContext) -> list[tuple[str, str]]:
    variants = [("original", ctx.original_query)]
    for i, generated in enumerate(ctx.generated_queries):
        variants.append((f"mq{i}", generated))
    if ctx.hyde_answer:
        variants.append(("hyde", ctx.hyde_answer))
    return variants


class HybridRetrieveStage:
    name = "hybrid_retrieve"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        engine = ctx.engine
        hybrid = engine.config.hybrid
        variants = _query_variants(ctx)

        if len(variants) == 1 and not hybrid.enabled:
            try:
                query_vector = embed_query(engine.model, variants[0][1])
                hits = engine.store.search(query_vector, top_k=ctx.top_k)
            except Exception as exc:
                raise RAGError(f"retrieval failed: {exc}", category="dependency") from exc
            ctx.candidates = [Candidate.from_result(hit, source="dense") for hit in hits]
            return ctx

        dense_top_k = hybrid.dense_top_k if hybrid.enabled else ctx.top_k

        try:
            vectors = embed_texts(engine.model, [text for _, text in variants])
        except Exception as exc:
            raise RAGError(f"embedding failed: {exc}", category="dependency") from exc

        def _search(labeled_vector: tuple[str, list[float]]) -> tuple[str, list[RetrievalResult]]:
            label, vector = labeled_vector
            try:
                return label, engine.store.search(vector, top_k=dense_top_k)
            except Exception as exc:
                raise RAGError(f"retrieval failed ({label}): {exc}", category="dependency") from exc

        search_args = list(zip((label for label, _ in variants), vectors))
        with ThreadPoolExecutor(max_workers=min(8, len(search_args))) as pool:
            variant_results = list(pool.map(_search, search_args))

        chunks_by_id: dict[str, LegislationChunk] = {}
        ranked_id_lists: list[list[str]] = []
        dense_scores: dict[str, float] = {}
        for _label, hits in variant_results:
            ranked_id_lists.append([hit.chunk.id for hit in hits])
            for hit in hits:
                chunks_by_id.setdefault(hit.chunk.id, hit.chunk)
                dense_scores[hit.chunk.id] = max(dense_scores.get(hit.chunk.id, 0.0), hit.score)

        bm25_scores: dict[str, float] = {}
        if hybrid.enabled:
            try:
                bm25_hits = engine.bm25_index.search(ctx.original_query, top_k=hybrid.bm25_top_k, store=engine.store)
            except Exception as exc:
                raise RAGError(f"bm25 retrieval failed: {exc}", category="dependency") from exc
            ranked_id_lists.append([chunk.id for chunk, _ in bm25_hits])
            for chunk, score in bm25_hits:
                chunks_by_id.setdefault(chunk.id, chunk)
                bm25_scores[chunk.id] = score

        if hybrid.enabled and hybrid.fusion == "weighted":
            fused = weighted_fusion(dense_scores, bm25_scores, alpha=hybrid.alpha)
        else:
            fused = reciprocal_rank_fusion(ranked_id_lists, k=hybrid.rrf_k)

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
