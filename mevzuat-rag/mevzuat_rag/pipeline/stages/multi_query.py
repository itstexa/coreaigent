"""[1] Multi-Query — asks the LLM for N different-angle search queries
(paraphrase-free) from the original question, so [2] Hybrid Retrieve fans
out over all of them instead of just the literal query.

The prompt template lives in prompts/multi_query.txt (not hardcoded — spec:
"Üretim şablonu prompt dosyasında dursun, kodda gömülü olmasın"). If the LLM
response isn't valid JSON (or isn't a list of strings), this falls back to
the original query only — HybridRetrieveStage already always searches with
ctx.original_query regardless of ctx.generated_queries, so a fallback here
never breaks retrieval, it just skips the extra angles for this query.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from mevzuat_rag.llm_client import get_client
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.retry import call_with_retry

logger = logging.getLogger("mevzuat_rag.multi_query")

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROMPT_PATH = PROJECT_ROOT / "prompts" / "multi_query.txt"


def _parse_queries(raw_text: str, n: int) -> list[str]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    parsed = json.loads(text)
    if not isinstance(parsed, list) or not all(isinstance(q, str) for q in parsed):
        raise ValueError("beklenen format: string listesi")
    return [q.strip() for q in parsed if q.strip()][:n]


class MultiQueryStage:
    name = "multi_query"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.engine.config.multi_query
        gen_config = ctx.engine.config.generation

        prompt_path = Path(config.prompt_path)
        if not prompt_path.is_absolute():
            prompt_path = PROJECT_ROOT / config.prompt_path
        template = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else DEFAULT_PROMPT_PATH.read_text(encoding="utf-8")
        prompt = template.format(query=ctx.original_query, n=config.n_queries)

        client = get_client()

        def _call():
            return client.chat.completions.create(
                model=gen_config.model,
                temperature=0.7,
                max_tokens=400,
                timeout=gen_config.timeout_s,
                messages=[{"role": "user", "content": prompt}],
            )

        try:
            response = call_with_retry(_call, attempts=gen_config.retry_attempts, backoff_base_s=gen_config.retry_backoff_s)
            ctx.generated_queries = _parse_queries(response.choices[0].message.content, config.n_queries)
        except Exception as exc:
            logger.warning("Multi-Query üretilemedi (%s) — yalnızca orijinal sorguyla devam ediliyor.", exc)
            ctx.generated_queries = []

        return ctx
