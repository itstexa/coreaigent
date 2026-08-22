"""[3] Rerank — cross-encoder reranker narrows Hybrid Retrieve's candidate
set down to top_n by relevance. Backend is swappable behind
``rerank(query, candidates, top_n)`` — CrossEncoderReranker here; an API- or
LLM-based backend can implement the same shape later without touching this
stage.

Graceful degradation (spec: "Reranker yüklenemezse: crash etme, uyarı logla,
hybrid skorlarıyla devam et"): if the model fails to load or score, this
stage logs a WARNING and leaves ctx.candidates in hybrid-retrieve order,
truncated to ctx.top_k, instead of raising.

[Retrieval #2] Adaptif rerank kesimi (docs/IMPROVEMENT_IDEAS.md) — gerçek
skor dağılımları soruya göre çok değişken: bazen tek net cevap (dar/keskin
düşüş), bazen birden fazla alakalı madde (geniş/yumuşak düşüş). min_score
zaten zayıf sonuçları eliyor ama sabit top_n üst kesimi hâlâ kördür.
``config.adaptive_cutoff=True`` iken, sabit top_n yerine ardışık skorlar
arasındaki ilk büyük orantısal düşüşü (elbow/gap) bulup oradan keser — en az
1, en fazla ``top_n * 1.5`` aday tutarak. Varsayılan (adaptive_cutoff=False)
davranış değişmez: mevcut sabit top_n kesimi aynen korunur.
"""
from __future__ import annotations

import logging
import math

from mevzuat_rag.pipeline.context import PipelineContext

logger = logging.getLogger("mevzuat_rag.rerank")

_model_cache: dict[str, object] = {}


def _get_cross_encoder(model_name: str, device: str):
    if model_name not in _model_cache:
        from sentence_transformers import CrossEncoder

        _model_cache[model_name] = CrossEncoder(model_name, device=device)
    return _model_cache[model_name]


def _adaptive_cutoff_count(scores: list[float], top_n: int, drop_ratio: float) -> int:
    """Skor listesindeki (yüksekten düşüğe sıralı) ilk büyük orantısal
    düşüşü bulup, o noktaya kadar kaç aday tutulacağını döndürür.

    - Arama yalnızca ``[1, ceil(top_n * 1.5)]`` penceresinde yapılır — hem
      alt sınır (en az 1 aday) hem üst sınır (top_n'in en fazla 1.5 katı)
      burada garanti edilir, sonsuz büyüme mümkün değildir.
    - ``curr / prev < drop_ratio`` olan ilk ardışık çift bulunduğunda, bir
      önceki adaya kadar (o dahil) kesim yapılır — yani düşüşten *önceki*
      adaylar tutulur.
    - Pencere içinde hiç düşüş bulunmazsa (skorlar yumuşak/düz azalıyorsa),
      davranış eski sabit top_n kesimine geriler (ama pencere kadar aday
      varsa onunla sınırlı kalır).
    - ``prev <= 0`` olan çiftlerde oran hesaplanamaz (bölme hatası / anlamsız
      sonuç); bu çiftler atlanır, düşüş sayılmaz.
    """
    n = len(scores)
    if n == 0:
        return 0

    max_keep = max(1, min(n, math.ceil(top_n * 1.5)))
    for i in range(1, max_keep):
        prev, curr = scores[i - 1], scores[i]
        if prev <= 0:
            continue
        if curr / prev < drop_ratio:
            return i

    return min(top_n, max_keep) if top_n > 0 else max_keep


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
        filtered = [c for c in ranked if c.score >= config.min_score]

        if getattr(config, "adaptive_cutoff", False):
            keep_n = _adaptive_cutoff_count(
                [c.score for c in filtered], config.top_n, config.adaptive_drop_ratio
            )
            ctx.candidates = filtered[:keep_n]
        else:
            # Geriye dönük uyumlu varsayılan davranış — değişmedi.
            ctx.candidates = filtered[: config.top_n]
        return ctx
