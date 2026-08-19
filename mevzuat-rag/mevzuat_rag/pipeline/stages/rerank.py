"""[3] Rerank — cross-encoder reranker narrows Hybrid Retrieve's candidate
set down to top_n by relevance. Backend is swappable behind
``rerank(query, candidates, top_n)`` — CrossEncoderReranker here; an API- or
LLM-based backend can implement the same shape later without touching this
stage.

Graceful degradation (spec: "Reranker yüklenemezse: crash etme, uyarı logla,
hybrid skorlarıyla devam et"): if the model fails to load or score, this
stage logs a WARNING and leaves ctx.candidates in hybrid-retrieve order,
truncated to ctx.top_k, instead of raising.
"""
from __future__ import annotations

import logging

from mevzuat_rag.pipeline.context import PipelineContext

logger = logging.getLogger("mevzuat_rag.rerank")

_model_cache: dict[str, object] = {}


def _get_cross_encoder(model_name: str, device: str):
    if model_name not in _model_cache:
        from sentence_transformers import CrossEncoder

        _model_cache[model_name] = CrossEncoder(model_name, device=device)
    return _model_cache[model_name]


class RerankStage:
    name = "rerank"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.engine.config.rerank
        if not ctx.candidates:
            return ctx

        try:
            model = _get_cross_encoder(config.model, ctx.engine.config.device)
            pairs = [(ctx.original_query, candidate.text) for candidate in ctx.candidates]
            scores = model.predict(pairs)
        except Exception as exc:
            logger.warning("Reranker kullanılamıyor (%s) — hybrid skorlarıyla devam ediliyor.", exc)
            ctx.candidates = ctx.candidates[: ctx.top_k]
            return ctx

        for candidate, score in zip(ctx.candidates, scores):
            candidate.metadata["rerank_score"] = float(score)
            candidate.score = float(score)
            candidate.source = "reranked"

        ranked = sorted(ctx.candidates, key=lambda c: c.score, reverse=True)
        ctx.candidates = [c for c in ranked if c.score >= config.min_score][: config.top_n]
        return ctx
