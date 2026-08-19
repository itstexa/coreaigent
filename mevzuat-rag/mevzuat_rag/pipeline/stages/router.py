"""[0] Self-RAG Router — decides RETRIEVE / ANSWER_DIRECTLY / CLARIFY before
touching the vector store, as structured JSON ({decision, confidence,
reason}). Safety rule (hard-coded into the system prompt, not a suggestion):
any doubt about whether the question needs domain-specific/current/numeric/
internal-document knowledge must resolve to RETRIEVE — this is a legal-
citation system, a confidently wrong ANSWER_DIRECTLY is worse than an
unnecessary retrieval. Router failures (bad JSON, API error) fail the same
way: RETRIEVE.

Sets ``ctx.stopped = True`` for a non-RETRIEVE decision, which short-
circuits every later stage (see pipeline/runner.py) — retrieve() then
naturally returns [] (no stage ever populated ctx.candidates) and ask()
returns the router's own direct/clarify reply instead of calling DeepSeek's
grounded-generation path.
"""
from __future__ import annotations

import json
import logging

from mevzuat_rag.llm_client import get_client
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.retry import call_with_retry

logger = logging.getLogger("mevzuat_rag.router")

SYSTEM_PROMPT = (
    "Sen bir Türk mevzuatı asistanının ön-yönlendiricisisin. Kullanıcının "
    "sorusu için üç karardan birini ver:\n"
    "- RETRIEVE: soru mevzuat/hukuki bilgi, güncel/sayısal bir bilgi ya da "
    "iç dokümana dayalı bir cevap gerektiriyor.\n"
    "- ANSWER_DIRECTLY: soru selamlama, teşekkür, asistanın kendisi "
    "hakkında ya da mevzuatla hiç ilgisi olmayan genel bir sohbet cümlesi.\n"
    "- CLARIFY: soru o kadar belirsiz ki ne arandığı anlaşılamıyor, "
    "kullanıcıdan netleştirme istenmeli.\n\n"
    "ÖNEMLİ GÜVENLİK KURALI: Emin değilsen, soru mevzuata dair olabilir mi "
    "diye en ufak bir şüphen varsa, DAİMA RETRIEVE seç. Yanlış bir "
    "ANSWER_DIRECTLY kararı gerçek zarar riski taşır.\n\n"
    "Yalnızca şu JSON formatında cevap ver, başka hiçbir açıklama ekleme:\n"
    '{"decision": "RETRIEVE" | "ANSWER_DIRECTLY" | "CLARIFY", '
    '"confidence": 0.0-1.0, "reason": "kısa gerekçe"}'
)

_DIRECT_ANSWERS = {
    "ANSWER_DIRECTLY": (
        "Ben Türk mevzuatı üzerine çalışan bir RAG asistanıyım. Kanun/yönetmelik "
        "maddeleriyle ilgili somut bir soru sorarsanız, ilgili mevzuata atıfla "
        "cevap verebilirim."
    ),
    "CLARIFY": (
        "Sorunuzu tam olarak anlayamadım — hangi kanun/yönetmelik veya konu "
        "hakkında bilgi almak istediğinizi biraz daha açar mısınız?"
    ),
}


def _parse_decision(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    parsed = json.loads(text)
    decision = parsed.get("decision")
    if decision not in ("RETRIEVE", "ANSWER_DIRECTLY", "CLARIFY"):
        raise ValueError(f"beklenmeyen decision: {decision!r}")
    return {
        "decision": decision,
        "confidence": float(parsed.get("confidence", 0.5)),
        "reason": str(parsed.get("reason", "")),
    }


class RouterStage:
    name = "router"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        gen_config = ctx.engine.config.generation
        client = get_client()

        def _call():
            return client.chat.completions.create(
                model=ctx.engine.config.router.model,
                temperature=0.0,
                max_tokens=150,
                timeout=gen_config.timeout_s,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": ctx.original_query},
                ],
            )

        try:
            response = call_with_retry(_call, attempts=gen_config.retry_attempts, backoff_base_s=gen_config.retry_backoff_s)
            decision = _parse_decision(response.choices[0].message.content)
        except Exception as exc:
            logger.warning("Router kararı alınamadı (%s) — güvenlik kuralı gereği RETRIEVE'e düşülüyor.", exc)
            decision = {"decision": "RETRIEVE", "confidence": 0.0, "reason": f"router failed: {exc}"}

        ctx.decision = decision

        if decision["decision"] != "RETRIEVE":
            ctx.stopped = True
            ctx.stopped_reason = f"router:{decision['decision'].lower()}"
            ctx.answer = {
                "answer": _DIRECT_ANSWERS[decision["decision"]],
                "citations": [],
                "sources": [],
                "router_decision": decision,
            }

        return ctx
