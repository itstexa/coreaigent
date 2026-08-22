"""[8] Post-hoc Atıf Doğrulama — [7] Generate'in ürettiği cevaptaki [N]
atıflarını doğrular. İki bağımsız katman, sırayla:

1. **Yapısal kontrol** (LLM gerektirmez, ücretsiz): cevapta geçen her [N]
   işareti gerçekten ``sources`` listesinde var mı? Bir modelin var olmayan
   bir kaynağa atıf yapması (ör. yalnızca 3 kaynak verilmişken [4] demesi)
   bilinen, ucuz tespit edilebilir bir halüsinasyon türü — bulunursa LLM
   çağrısına hiç gerek kalmadan doğrudan reddedilir.
2. **Kanıt kontrolü** (LLM gerektirir, ``config.llm_check`` ile ayrıca
   kapatılabilir): yapısal kontrolü geçen her iddianın gerçekten o kaynakta
   geçip geçmediğini ayrı bir DeepSeek çağrısıyla sorar — crag.py'nin
   ``_evaluate``'iyle aynı desen. CRAG üretimden ÖNCE "kanıt yeterli mi"
   diye sorar; bu, üretimden SONRA gerçekten o kanıta sadık kalınıp
   kalınmadığını sorar — farklı bir hata sınıfı: retrieval doğruydu ama LLM
   yine de yanlış/aşırı genelleyen bir cümle kurdu.

CRAG'daki "evaluator failure fails OPEN" politikasıyla aynı: LLM çağrısı
başarısız olursa (ağ, geçersiz key, timeout) orijinal cevap korunur, WARNING
loglanır — bu bir güvenlik katmanı, altyapı sorununda sistemi daha kırılgan
yapmamalı.

**Varsayılan kapalı** (``enabled: false``): bu depodaki her teknik gibi
("ikisi de doğrulandı ve varsayılan açık" — NOTES.md) gerçek bir DeepSeek
anahtarıyla uçtan uca doğrulanmadan açılmıyor; bu oturumda kullanılabilir bir
anahtar yoktu (bkz. rapor). Yapısal kontrol LLM'siz gerçek testlerle
doğrulandı; LLM kontrolü mock'lu testlerle doğrulandı, gerçek anahtarla
henüz değil.
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

_CITATION_RE = re.compile(r"\[(\d+)\]")

SYSTEM_PROMPT = (
    "Sen bir Türk mevzuatı RAG sisteminin son kontrol katısın. Sana bir cevap "
    "ve o cevabın dayandığını iddia ettiği kaynak parçalar verilecek. Cevaptaki "
    "iddiaların GERÇEKTEN kaynak parçalarda geçip geçmediğini değerlendir:\n"
    "- SUPPORTED: cevaptaki tüm iddialar kaynak parçalarda açıkça (veya doğrudan "
    "çıkarımla) destekleniyor.\n"
    "- UNSUPPORTED: cevap, kaynak parçalarda olmayan bir iddia içeriyor veya "
    "kaynakları yanlış yorumluyor.\n\n"
    "Yalnızca şu JSON formatında cevap ver, başka hiçbir açıklama ekleme:\n"
    '{"verdict": "SUPPORTED" | "UNSUPPORTED", "reason": "kısa gerekçe"}'
    + INJECTION_DEFENSE_NOTE
)


def _parse_verdict(raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    parsed = json.loads(text)
    verdict = parsed.get("verdict")
    if verdict not in ("SUPPORTED", "UNSUPPORTED"):
        raise ValueError(f"beklenmeyen verdict: {verdict!r}")
    return {"verdict": verdict, "reason": str(parsed.get("reason", ""))}


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

        if answer_text.strip() == REFUSAL_TEXT or not sources:
            return ctx  # zaten ret ya da kaynak yok — doğrulanacak bir şey yok

        bad_indices = _structural_check(answer_text, len(sources))
        if bad_indices:
            logger.warning(
                "Yapısal atıf hatası: cevap [%s] indeksine atıfta bulunuyor ama yalnızca %d kaynak var — reddediliyor.",
                ", ".join(str(i) for i in bad_indices), len(sources),
            )
            ctx.answer["answer"] = REFUSAL_TEXT
            ctx.answer["citations"] = []
            ctx.answer["post_hoc_verdict"] = "STRUCTURAL_FAIL"
            return ctx

        if not config.llm_check:
            ctx.answer["post_hoc_verdict"] = "STRUCTURAL_OK_UNCHECKED"
            return ctx

        source_block = "\n\n".join(f"[{i}] {wrap_source(s['text'])}" for i, s in enumerate(sources, start=1))
        user_prompt = f"Cevap:\n{answer_text}\n\nKaynak parçalar:\n{source_block}"
        client = get_client()

        def _call():
            return client.chat.completions.create(
                model=config.model,
                temperature=0.0,
                max_tokens=200,
                timeout=30.0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )

        try:
            response = call_with_retry(_call, attempts=2, backoff_base_s=1.0)
            verdict = _parse_verdict(response.choices[0].message.content)
        except Exception as exc:
            logger.warning("Post-hoc atıf doğrulama başarısız (%s) — orijinal cevap korunuyor.", exc)
            ctx.answer["post_hoc_verdict"] = "EVALUATOR_FAILED_OPEN"
            return ctx

        ctx.answer["post_hoc_verdict"] = verdict["verdict"]
        if verdict["verdict"] == "UNSUPPORTED":
            logger.warning("Atıf kaynakla tutmuyor (%s) — cevap reddediliyor.", verdict["reason"])
            ctx.answer["answer"] = REFUSAL_TEXT
            ctx.answer["citations"] = []

        return ctx
