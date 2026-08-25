"""[8] Hakem Ajan (Critic Agent) — [7] Generate'in ürettiği cevabı, kullanıcıya
gösterilmeden önce denetler. İki bağımsız katman, sırayla:

1. **Yapısal kontrol** (LLM gerektirmez, ücretsiz): cevapta geçen her [N]
   işareti gerçekten ``sources`` listesinde var mı? Bir modelin var olmayan
   bir kaynağa atıf yapması (ör. yalnızca 3 kaynak verilmişken [4] demesi)
   bilinen, ucuz tespit edilebilir bir halüsinasyon türü — bulunursa LLM
   çağrısına hiç gerek kalmadan doğrudan engellenir.
2. **Hakem Ajan kontrolü** (LLM gerektirir, ``config.llm_check`` ile ayrıca
   kapatılabilir, bkz. ``verify_answer()``): yapısal kontrolü geçen cevabın
   bağlamla (kanun maddeleriyle) tamamen tutarlı olup olmadığını sert bir
   "hukuki denetçi" persona'sıyla ayrı bir DeepSeek çağrısında sorar —
   crag.py'nin ``_evaluate``'iyle aynı desen. CRAG üretimden ÖNCE "kanıt
   yeterli mi" diye sorar; bu, üretimden SONRA gerçekten o kanıta sadık
   kalınıp kalınmadığını sorar — farklı bir hata sınıfı: retrieval doğruydu
   ama LLM yine de yanlış/aşırı genelleyen bir cümle kurdu.

CRAG'daki "evaluator failure fails OPEN" politikasıyla aynı: LLM çağrısı
başarısız olursa (ağ, geçersiz key, timeout) orijinal cevap korunur, WARNING
loglanır — bu bir güvenlik katmanı, altyapı sorununda sistemi daha kırılgan
yapmamalı.
"""
from __future__ import annotations

import json
import logging
import re

from mevzuat_rag.llm_client import get_client
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.prompt_safety import INJECTION_DEFENSE_NOTE, wrap_source
from mevzuat_rag.retry import call_with_retry

logger = logging.getLogger("mevzuat_rag.post_hoc_verify")

REFUSAL_TEXT = "Verilen mevzuat parçalarında bu sorunun cevabı yok."

HAKEM_BLOCKED_TEXT = (
    "Üretilen cevap, mevzuat maddeleriyle çeliştiği veya halüsinasyon "
    "içerdiği için güvenlik sistemi (Hakem Ajan) tarafından engellenmiştir. "
    "Lütfen soruyu daraltın."
)

_CITATION_RE = re.compile(r"\[(\d+)\]")

CRITIC_SYSTEM_PROMPT = (
    "Sen sert bir hukuki denetçisin (Hakem Ajan). Sana bir Türk mevzuatı RAG "
    "sisteminin ürettiği bir cevap ve o cevabın dayanması gereken bağlam "
    "(kanun/yönetmelik maddeleri) verilecek.\n\n"
    "Aşağıdaki üretilen cevap, verilen bağlam (kanun maddeleri) ile "
    "tamamen destekleniyor mu? Eğer cevapta kanunda olmayan uydurma bir "
    "bilgi, yanlış bir süre/sayı veya kaynaksız bir ekleme varsa KESİNLİKLE "
    "REDDET. Cevap bağlamdaki maddelerle çelişiyorsa da KESİNLİKLE REDDET. "
    "Cevabın tamamı bağlamla tutarlıysa ONAYLA.\n\n"
    "Yalnızca şu JSON formatında cevap ver, başka hiçbir açıklama ekleme:\n"
    '{"is_valid": true veya false, "reason": "kısa gerekçe"}'
    + INJECTION_DEFENSE_NOTE
)


def _parse_critic_verdict(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    parsed = json.loads(text)
    is_valid = parsed.get("is_valid")
    if not isinstance(is_valid, bool):
        raise ValueError(f"beklenmeyen is_valid: {is_valid!r}")
    return {"is_valid": is_valid, "reason": str(parsed.get("reason", ""))}


def verify_answer(
    generated_answer: str,
    retrieved_chunks: list[dict],
    model: str = "deepseek-chat",
    client=None,
    timeout_s: float = 30.0,
    retry_attempts: int = 2,
    retry_backoff_s: float = 1.0,
) -> dict:
    """Hakem Ajan: üretilen cevabı verilen bağlamla karşılaştırıp
    ``{"is_valid": bool, "reason": str}`` döner.

    ``retrieved_chunks``: ``[{"citation": str, "text": str}, ...]`` biçiminde
    — ``ctx.answer["sources"]`` ile aynı şekil. ``RAGEngine.retrieve()``'den
    dönen ``RetrievalResult`` listesiyle çağıracaksan:
    ``[{"citation": h.chunk.citation, "text": h.chunk.text} for h in hits]``.

    LLM çağrısı burada YAKALANMAZ (ağ/geçersiz key hatası olduğu gibi
    dışarı fırlatılır) — "fails open" kararı çağıran tarafın (ör.
    ``PostHocVerifyStage``) sorumluluğundadır, ``verify_answer`` yalnızca
    denetim mantığını uygular.
    """
    source_block = "\n\n".join(
        f"[{i}] {wrap_source(c.get('text', ''))}" for i, c in enumerate(retrieved_chunks, start=1)
    )
    user_prompt = f"Üretilen cevap:\n{generated_answer}\n\nBağlam (kanun maddeleri):\n{source_block}"
    client = client or get_client()

    def _call():
        return client.chat.completions.create(
            model=model,
            temperature=0.0,
            max_tokens=200,
            timeout=timeout_s,
            messages=[
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

    response = call_with_retry(_call, attempts=retry_attempts, backoff_base_s=retry_backoff_s)
    return _parse_critic_verdict(response.choices[0].message.content)


def _structural_check(answer_text: str, n_sources: int) -> list[int]:
    """Cevapta geçip sources listesinde karşılığı olmayan atıf indekslerini
    döndürür (boşsa yapısal olarak temiz demektir)."""
    cited = {int(m.group(1)) for m in _CITATION_RE.finditer(answer_text)}
    return sorted(i for i in cited if i < 1 or i > n_sources)


class PostHocVerifyStage:
    name = "post_hoc_verify"

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.engine.config.post_hoc_verify
        if ctx.answer is None or not ctx.answer.get("answer"):
            return ctx

        answer_text = ctx.answer["answer"]
        sources = ctx.answer.get("sources", [])

        if answer_text.strip() in (REFUSAL_TEXT, HAKEM_BLOCKED_TEXT) or not sources:
            return ctx  # zaten ret/engellenmiş ya da kaynak yok — doğrulanacak bir şey yok

        bad_indices = _structural_check(answer_text, len(sources))
        if bad_indices:
            logger.warning(
                "Yapısal atıf hatası: cevap [%s] indeksine atıfta bulunuyor ama yalnızca %d kaynak var — Hakem Ajan tarafından engellendi.",
                ", ".join(str(i) for i in bad_indices), len(sources),
            )
            ctx.answer["answer"] = HAKEM_BLOCKED_TEXT
            ctx.answer["citations"] = []
            ctx.answer["post_hoc_verdict"] = "STRUCTURAL_FAIL"
            ctx.answer["post_hoc_reason"] = f"var olmayan kaynağa atıf: {bad_indices}"
            return ctx

        if not config.llm_check:
            ctx.answer["post_hoc_verdict"] = "STRUCTURAL_OK_UNCHECKED"
            return ctx

        try:
            verdict = verify_answer(answer_text, sources, model=config.model)
        except Exception as exc:
            logger.warning("Hakem Ajan denetimi başarısız (%s) — orijinal cevap korunuyor (fails open).", exc)
            ctx.answer["post_hoc_verdict"] = "EVALUATOR_FAILED_OPEN"
            return ctx

        ctx.answer["post_hoc_reason"] = verdict["reason"]
        if verdict["is_valid"]:
            ctx.answer["post_hoc_verdict"] = "VALID"
        else:
            logger.warning("Hakem Ajan cevabı engelledi (%s).", verdict["reason"])
            ctx.answer["post_hoc_verdict"] = "REJECTED_BY_CRITIC"
            ctx.answer["answer"] = HAKEM_BLOCKED_TEXT
            ctx.answer["citations"] = []

        return ctx
