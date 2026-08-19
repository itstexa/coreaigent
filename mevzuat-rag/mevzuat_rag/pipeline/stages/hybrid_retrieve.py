"""[2] Hybrid Retrieve — dense (vector) search, always; sparse (BM25) search
+ RRF/weighted fusion land in checkpoint 2 once ``config.hybrid.enabled`` is
wired up (see mevzuat_rag/pipeline/fusion.py, added then). Until that lands,
this stage reproduces exactly the pre-pipeline dense-only retrieve() behavior
(same top_k, same store.search call).

Embeds ``ctx.hyde_answer`` instead of the raw query when HyDE has set it
(checkpoint 3) — no change needed here when that stage is added.
"""
from __future__ import annotations

from mevzuat_rag.embedding import embed_query
from mevzuat_rag.errors import RAGError
from mevzuat_rag.pipeline.candidate import Candidate
from mevzuat_rag.pipeline.context import PipelineContext


class HybridRetrieveStage:
    name = "hybrid_retrieve"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        engine = ctx.engine
        query_text = ctx.hyde_answer or ctx.original_query

        try:
            query_vector = embed_query(engine.model, query_text)
        except Exception as exc:
            raise RAGError(f"embedding failed: {exc}", category="dependency") from exc

        try:
            hits = engine.store.search(query_vector, top_k=ctx.top_k)
        except Exception as exc:
            raise RAGError(f"retrieval failed: {exc}", category="dependency") from exc

        ctx.candidates = [Candidate.from_result(hit, source="dense") for hit in hits]
        return ctx
