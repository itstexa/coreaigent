"""[1] HyDE — for short/ambiguous queries (estimated token count at or under
``hyde.trigger_max_tokens``), asks the LLM for a short hypothetical answer
and lets [2] Hybrid Retrieve embed *that* instead of (in addition to,
depending on hybrid_retrieve's variant fan-out) the raw query. Not triggered
on every query — only short ones, per spec.

Graceful fallback: if the LLM call fails, ``ctx.hyde_answer`` stays None and
retrieval proceeds on the original query only, same as if HyDE were
disabled for this query.
"""
from __future__ import annotations

import logging

from mevzuat_rag.llm_client import get_client
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.retry import call_with_retry
from mevzuat_rag.token_estimate import estimate_tokens

logger = logging.getLogger("mevzuat_rag.hyde")

SYSTEM_PROMPT = (
    "Sen bir Türk mevzuatı asistanısın. Kullanıcının sorusuna, gerçek bir "
    "kanun/yönetmelik maddesinde geçebilecek tarzda KISA bir hipotetik "
    "cevap yaz (uydurma bir madde numarası verme, sadece konuya uygun bir "
    "cevap metni üret — bu metin arama için kullanılacak, gerçek cevap "
    "olarak sunulmayacak)."
)


class HyDEStage:
    name = "hyde"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.resolved_config.hyde
        if estimate_tokens(ctx.original_query) > config.trigger_max_tokens:
            return ctx  # not short/ambiguous enough to trigger HyDE

        gen_config = ctx.engine.config.generation
        client = get_client(api_key=gen_config.api_key, base_url=gen_config.base_url)

        def _call():
            return client.chat.completions.create(
                model=gen_config.model,
                temperature=0.3,
                max_tokens=config.max_answer_tokens,
                timeout=gen_config.timeout_s,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": ctx.original_query},
                ],
            )

        try:
            response = call_with_retry(_call, attempts=gen_config.retry_attempts, backoff_base_s=gen_config.retry_backoff_s)
            ctx.hyde_answer = response.choices[0].message.content.strip() or None
        except Exception as exc:
            logger.warning("HyDE hipotetik cevabı üretilemedi (%s) — orijinal sorguyla devam ediliyor.", exc)
            ctx.hyde_answer = None

        return ctx
