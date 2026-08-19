"""[5] CRAG (Corrective RAG) — judges whether [2]-[4]'s candidates actually
answer the query (SUFFICIENT/PARTIAL/INSUFFICIENT, structured LLM verdict)
and corrects when they don't:

- PARTIAL: asks the evaluator what's missing (as a short follow-up search
  query), retrieves specifically for that gap, merges the new candidates in
  (dedup by chunk id, keep the higher score), then re-reranks/re-expands.
- INSUFFICIENT: applies ``config.crag.insufficient_strategy``:
    * "force_hyde": generates a hypothetical answer unconditionally (not
      gated by hyde.trigger_max_tokens — CRAG already decided the current
      approach failed) and retrieves with it.
    * "shift_to_bm25": adds a fresh BM25-only pass (keyword matching can
      catch what dense embedding similarity missed).
    * "refuse": clears candidates so [7] Generate's built-in "no answer in
      the given text" refusal fires — no fabrication.

Hard-capped at ``config.crag.max_loops`` — cannot loop forever. Evaluator
failures fail OPEN to SUFFICIENT (proceed with whatever is already
retrieved; Generate's own grounding/refusal behavior is the real safety
net, not this stage), logged as a WARNING.

Deliberately does NOT mutate ``ctx.engine.config`` to apply a strategy (that
would leak into concurrent/future requests on the same shared RAGEngine) —
every correction here works directly off ``ctx``/engine.store/engine.model.
"""
from __future__ import annotations

import json
import logging

from mevzuat_rag.embedding import embed_query
from mevzuat_rag.llm_client import get_client
from mevzuat_rag.models import RetrievalResult
from mevzuat_rag.pipeline.candidate import Candidate
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.text_norm import normalize_text
from mevzuat_rag.pipeline.stages.hyde import SYSTEM_PROMPT as HYDE_SYSTEM_PROMPT
from mevzuat_rag.pipeline.stages.parent_doc import ParentDocStage
from mevzuat_rag.pipeline.stages.rerank import RerankStage
from mevzuat_rag.retry import call_with_retry

logger = logging.getLogger("mevzuat_rag.crag")

SYSTEM_PROMPT = (
    "Sen bir Türk mevzuatı RAG sisteminin kalite değerlendiricisisin. Sana "
    "bir soru ve o soru için getirilmiş mevzuat parçaları verilecek. Bu "
    "parçaların soruyu CEVAPLAMAYA yeterli olup olmadığını değerlendir:\n"
    "- SUFFICIENT: parçalar soruyu tam cevaplıyor.\n"
    "- PARTIAL: parçalar sorunun bir kısmını cevaplıyor ama eksik bir yön var.\n"
    "- INSUFFICIENT: parçalar soruyla alakasız veya soruyu hiç cevaplamıyor.\n\n"
    "Yalnızca şu JSON formatında cevap ver, başka hiçbir açıklama ekleme:\n"
    '{"verdict": "SUFFICIENT" | "PARTIAL" | "INSUFFICIENT", '
    '"missing_aspect": "PARTIAL ise eksik olan şeyi arayacak kısa bir sorgu, değilse boş string", '
    '"reason": "kısa gerekçe"}'
)


def _parse_verdict(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    parsed = json.loads(text)
    verdict = parsed.get("verdict")
    if verdict not in ("SUFFICIENT", "PARTIAL", "INSUFFICIENT"):
        raise ValueError(f"beklenmeyen verdict: {verdict!r}")
    return {
        "verdict": verdict,
        "missing_aspect": str(parsed.get("missing_aspect", "")),
        "reason": str(parsed.get("reason", "")),
    }


def _merge(existing: list[Candidate], new: list[Candidate]) -> list[Candidate]:
    by_id = {c.id: c for c in existing}
    for candidate in new:
        current = by_id.get(candidate.id)
        if current is None or candidate.score > current.score:
            by_id[candidate.id] = candidate
    return sorted(by_id.values(), key=lambda c: c.score, reverse=True)


class CRAGStage:
    name = "crag"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def _evaluate(self, ctx: PipelineContext) -> dict:
        gen_config = ctx.engine.config.generation
        context = "\n\n".join(f"({c.chunk.citation}) {c.text}" for c in ctx.candidates) or "(hiç sonuç bulunamadı)"
        user_prompt = f"Soru: {ctx.original_query}\n\nGetirilen parçalar:\n{context}"
        client = get_client()

        def _call():
            return client.chat.completions.create(
                model=gen_config.model,
                temperature=0.0,
                max_tokens=200,
                timeout=gen_config.timeout_s,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )

        try:
            response = call_with_retry(_call, attempts=gen_config.retry_attempts, backoff_base_s=gen_config.retry_backoff_s)
            return _parse_verdict(response.choices[0].message.content)
        except Exception as exc:
            logger.warning("CRAG değerlendirmesi başarısız (%s) — SUFFICIENT'e düşülüp mevcut sonuçla devam ediliyor.", exc)
            return {"verdict": "SUFFICIENT", "missing_aspect": "", "reason": f"evaluator failed: {exc}"}

    def _retrieve_for(self, ctx: PipelineContext, query_text: str, top_k: int) -> list[Candidate]:
        engine = ctx.engine
        vector = embed_query(engine.model, normalize_text(query_text, profile="embedding"))
        hits = engine.store.search(vector, top_k=top_k)
        return [Candidate.from_result(hit, source="crag_refine") for hit in hits]

    def _apply_insufficient_strategy(self, ctx: PipelineContext) -> None:
        strategy = ctx.engine.config.crag.insufficient_strategy
        engine = ctx.engine

        if strategy == "refuse":
            ctx.candidates = []
            return

        if strategy == "force_hyde":
            gen_config = engine.config.generation
            client = get_client()

            def _call():
                return client.chat.completions.create(
                    model=gen_config.model,
                    temperature=0.3,
                    max_tokens=engine.config.hyde.max_answer_tokens,
                    timeout=gen_config.timeout_s,
                    messages=[
                        {"role": "system", "content": HYDE_SYSTEM_PROMPT},
                        {"role": "user", "content": ctx.original_query},
                    ],
                )

            try:
                response = call_with_retry(_call, attempts=gen_config.retry_attempts, backoff_base_s=gen_config.retry_backoff_s)
                hyde_answer = response.choices[0].message.content.strip()
            except Exception as exc:
                logger.warning("CRAG force_hyde başarısız (%s) — orijinal sorguyla devam ediliyor.", exc)
                return
            if not hyde_answer:
                return
            ctx.hyde_answer = hyde_answer
            top_k = engine.config.hybrid.dense_top_k if engine.config.hybrid.enabled else ctx.top_k
            vector = embed_query(engine.model, normalize_text(hyde_answer, profile="embedding"))
            hits = engine.store.search(vector, top_k=top_k)
            new_candidates = [Candidate.from_result(hit, source="crag_hyde") for hit in hits]
            ctx.candidates = _merge(ctx.candidates, new_candidates)
            return

        if strategy == "shift_to_bm25":
            try:
                bm25_hits = engine.bm25_index.search(ctx.original_query, top_k=engine.config.hybrid.bm25_top_k, store=engine.store)
            except Exception as exc:
                logger.warning("CRAG shift_to_bm25 başarısız (%s).", exc)
                return
            new_candidates = [
                Candidate.from_result(RetrievalResult(chunk=chunk, score=score), source="crag_bm25")
                for chunk, score in bm25_hits
            ]
            ctx.candidates = _merge(ctx.candidates, new_candidates)

    def run(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.engine.config.crag

        for _ in range(config.max_loops):
            verdict = self._evaluate(ctx)
            ctx.crag_verdict = verdict["verdict"]

            if verdict["verdict"] == "SUFFICIENT":
                return ctx

            ctx.crag_loop_count += 1

            if verdict["verdict"] == "PARTIAL" and verdict["missing_aspect"]:
                new_candidates = self._retrieve_for(ctx, verdict["missing_aspect"], top_k=ctx.top_k)
                ctx.candidates = _merge(ctx.candidates, new_candidates)
            elif verdict["verdict"] == "INSUFFICIENT":
                self._apply_insufficient_strategy(ctx)
                if not ctx.candidates:
                    return ctx  # "refuse" strategy
            else:
                return ctx  # PARTIAL without a usable missing_aspect — nothing more to correct

            if ctx.engine.config.rerank.enabled:
                ctx = RerankStage(enabled=True).run(ctx)
            if ctx.engine.config.parent_doc.enabled:
                ctx = ParentDocStage(enabled=True).run(ctx)

        return ctx
