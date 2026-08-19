"""[6] Context Compression — targets a token BUDGET, not a fixed ratio:

(a) redundancy removal: candidates whose embeddings are near-duplicates
    (cosine > ``dedup_cosine_threshold``) are merged, keeping the
    higher-scored one and dropping the rest.
(b) extractive sentence selection: if the deduped set still exceeds
    ``token_budget``, each candidate's text is cut down to its sentences
    most relevant to the query (Turkish-tokenized term overlap), enough to
    fit an even per-candidate share of the budget.
(c) optional LLM summarization (``compression.llm_summarize``, off by
    default): last resort if (b) still doesn't fit — merges everything into
    one LLM-condensed candidate that keeps the [1]/[2].. citation markers.

Each step only runs if the previous one didn't already get under budget.
"""
from __future__ import annotations

import logging
import re

from mevzuat_rag.models import LegislationChunk
from mevzuat_rag.pipeline.candidate import Candidate
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.pipeline.tokenize_tr import tokenize
from mevzuat_rag.token_estimate import estimate_tokens

logger = logging.getLogger("mevzuat_rag.compression")

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _dedup(candidates: list[Candidate], vectors: list[list[float]], threshold: float) -> list[Candidate]:
    ranked = sorted(zip(candidates, vectors), key=lambda pair: pair[0].score, reverse=True)
    kept: list[Candidate] = []
    kept_vectors: list[list[float]] = []
    for candidate, vector in ranked:
        if any(_cosine(vector, kv) > threshold for kv in kept_vectors):
            continue
        kept.append(candidate)
        kept_vectors.append(vector)
    return kept


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def _extractive_select(text: str, query_terms: set[str], token_budget: int) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return text
    scored = sorted(
        ((len(set(tokenize(sentence)) & query_terms), i, sentence) for i, sentence in enumerate(sentences)),
        key=lambda triple: triple[0],
        reverse=True,
    )
    selected_idx: set[int] = set()
    used_tokens = 0
    for _overlap, i, sentence in scored:
        cost = estimate_tokens(sentence)
        if selected_idx and used_tokens + cost > token_budget:
            continue
        selected_idx.add(i)
        used_tokens += cost
    if not selected_idx:
        return text
    return " ".join(sentences[i] for i in sorted(selected_idx))


class CompressionStage:
    name = "compression"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.engine.config.compression
        if not ctx.candidates:
            return ctx

        from mevzuat_rag.embedding import embed_texts

        vectors = embed_texts(ctx.engine.model, [c.text for c in ctx.candidates])
        candidates = _dedup(ctx.candidates, vectors, config.dedup_cosine_threshold)

        if sum(estimate_tokens(c.text) for c in candidates) <= config.token_budget:
            ctx.candidates = candidates
            return ctx

        query_terms = set(tokenize(ctx.original_query))
        per_candidate_budget = max(20, config.token_budget // max(1, len(candidates)))
        for candidate in candidates:
            new_text = _extractive_select(candidate.text, query_terms, per_candidate_budget)
            candidate.text = new_text
            candidate.chunk.text = new_text

        if sum(estimate_tokens(c.text) for c in candidates) > config.token_budget and config.llm_summarize:
            candidates = self._llm_summarize(ctx, candidates, config.token_budget)

        ctx.candidates = candidates
        return ctx

    def _llm_summarize(self, ctx: PipelineContext, candidates: list[Candidate], token_budget: int) -> list[Candidate]:
        from mevzuat_rag.llm_client import get_client
        from mevzuat_rag.retry import call_with_retry

        gen_config = ctx.engine.config.generation
        context = "\n\n".join(f"[{i + 1}] ({c.chunk.citation})\n{c.text}" for i, c in enumerate(candidates))
        prompt = (
            f"Aşağıdaki mevzuat parçalarını, [1] [2] gibi referans numaralarını KORUYARAK, "
            f"yaklaşık {token_budget} token'ı geçmeyecek şekilde özetle. Hiçbir hukuki bilgiyi "
            f"uydurma, sadece verilenleri kısalt:\n\n{context}"
        )
        client = get_client()

        def _call():
            return client.chat.completions.create(
                model=gen_config.model,
                temperature=0.0,
                max_tokens=min(gen_config.max_tokens, token_budget * 2),
                timeout=gen_config.timeout_s,
                messages=[{"role": "user", "content": prompt}],
            )

        try:
            response = call_with_retry(_call, attempts=gen_config.retry_attempts, backoff_base_s=gen_config.retry_backoff_s)
            summary_text = response.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning("LLM özetleme başarısız (%s) — extractive sonuçla devam ediliyor.", exc)
            return candidates

        merged_chunk = LegislationChunk(
            id="compressed:" + "+".join(c.chunk.id for c in candidates),
            text=summary_text,
            metadata=candidates[0].chunk.metadata,
            citation="; ".join(c.chunk.citation for c in candidates),
        )
        best_score = max(c.score for c in candidates)
        return [
            Candidate(
                id=merged_chunk.id, text=summary_text, score=best_score, source="llm_compressed",
                parent_id=None, metadata={"merged_from": [c.chunk.citation for c in candidates]}, chunk=merged_chunk,
            )
        ]
