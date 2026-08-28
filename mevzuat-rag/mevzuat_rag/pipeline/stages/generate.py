"""[7] Generate — grounded, cited DeepSeek answer over ctx.candidates.
Reproduces exactly the pre-pipeline RAGEngine.ask() behavior (same
generation.generate_answer call, same "sources" shape). GenerationError
propagates uncaught, same as before — callers that want it handled catch it
themselves (see ask.py)."""
from __future__ import annotations

from mevzuat_rag import generation
from mevzuat_rag.pipeline.context import PipelineContext


class GenerateStage:
    name = "generate"

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        gen_config = ctx.engine.config.generation
        hits = [candidate.to_result() for candidate in ctx.candidates]
        result = generation.generate_answer(
            ctx.original_query,
            hits,
            model=gen_config.model,
            temperature=gen_config.temperature,
            max_tokens=gen_config.max_tokens,
            timeout_s=gen_config.timeout_s,
            retry_attempts=gen_config.retry_attempts,
            retry_backoff_s=gen_config.retry_backoff_s,
            api_key=gen_config.api_key,
            base_url=gen_config.base_url,
        )
        result["sources"] = [
            {"citation": hit.chunk.citation, "score": round(float(hit.score), 3), "text": hit.chunk.text}
            for hit in hits
        ]

        # CRAG'ın kalite değerlendiricisi hata verip SUFFICIENT'e sessizce
        # düşmüşse, aşağıdaki cevabın gerçekten yeterli kanıta dayanıp
        # dayanmadığı hiç kontrol edilmemiş demektir — bunu son kullanıcıya
        # da göstermeden geçmek "sessiz fail-open" olurdu (bkz. crag.py).
        if ctx.crag_evaluator_failed:
            result["crag_status"] = "EVALUATOR_FAILED_OPEN"
            result["answer"] = (
                "[⚠️ SONUÇ DOĞRULANAMADI: Bu cevabın mevzuata dayanak "
                "yeterliliği, bir teknik hata nedeniyle otomatik kalite "
                "kontrolünden (CRAG) geçirilemedi. Aşağıdaki cevabı ihtiyatla "
                "değerlendirin.]\n\n" + result["answer"]
            )
        elif ctx.crag_verdict is not None:
            result["crag_status"] = "OK"

        ctx.answer = result
        return ctx
