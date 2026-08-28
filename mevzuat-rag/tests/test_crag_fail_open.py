"""CRAG'ın değerlendirici LLM çağrısı başarısız olduğunda artık sessizce
SUFFICIENT'e düşmediğini, bunun yerine hem ctx üzerinde işaretlendiğini hem
de son kullanıcıya görünür bir uyarı olarak ulaştığını doğrular.

Denetim bulgusu: "CRAG fail-open onaysız" (rag_config_panel.py, madde 3) —
önceki davranış yalnızca logger.warning basıp SUFFICIENT dönüyordu, hiçbir
iz kullanıcıya ulaşmıyordu.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.pipeline.stages.crag import CRAGStage
from mevzuat_rag.pipeline.stages.generate import GenerateStage


def _make_ctx(candidates=None) -> PipelineContext:
    engine = SimpleNamespace(
        config=SimpleNamespace(
            generation=SimpleNamespace(
                model="deepseek-chat", timeout_s=1.0, retry_attempts=1, retry_backoff_s=0.0,
                temperature=0.0, max_tokens=800, api_key=None, base_url=None, json_mode=True,
            ),
            crag=SimpleNamespace(max_loops=2, insufficient_strategy="refuse"),
        )
    )
    return PipelineContext(original_query="test sorgu", engine=engine, top_k=5, candidates=candidates or [])


def test_evaluator_exception_marks_ctx_as_failed_open():
    ctx = _make_ctx()
    stage = CRAGStage(enabled=True)

    broken_client = MagicMock()
    broken_client.chat.completions.create.side_effect = RuntimeError("ağ hatası")

    with patch("mevzuat_rag.pipeline.stages.crag.get_client", return_value=broken_client):
        result_ctx = stage.run(ctx)

    assert result_ctx.crag_verdict == "SUFFICIENT"
    assert result_ctx.crag_evaluator_failed is True, (
        "CRAG değerlendiricisi hata verdiğinde ctx.crag_evaluator_failed "
        "True olmalı — aksi halde fail-open sessizce geçer."
    )
    assert "ağ hatası" in result_ctx.crag_failure_reason


def test_evaluator_success_does_not_mark_failed():
    ctx = _make_ctx()
    stage = CRAGStage(enabled=True)

    ok_client = MagicMock()
    ok_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"verdict": "SUFFICIENT", "missing_aspect": "", "reason": "ok"}'))]
    )

    with patch("mevzuat_rag.pipeline.stages.crag.get_client", return_value=ok_client):
        result_ctx = stage.run(ctx)

    assert result_ctx.crag_evaluator_failed is False
    assert result_ctx.crag_verdict == "SUFFICIENT"


def test_generate_stage_surfaces_visible_warning_on_crag_failure():
    """Adayları boş bırakarak generation.generate_answer'ın DeepSeek'e hiç
    gitmeden sabit ret metnini dönmesini sağlıyoruz — bu testin amacı LLM
    çağrısını değil, CRAG->Generate arasındaki uyarı aktarımını doğrulamak."""
    ctx = _make_ctx(candidates=[])
    ctx.crag_verdict = "SUFFICIENT"
    ctx.crag_evaluator_failed = True
    ctx.crag_failure_reason = "ağ hatası"

    ctx = GenerateStage(enabled=True).run(ctx)

    assert ctx.answer["crag_status"] == "EVALUATOR_FAILED_OPEN"
    assert "SONUÇ DOĞRULANAMADI" in ctx.answer["answer"], (
        "CRAG evaluator hatası, üretilen cevaba görünür bir uyarı olarak "
        "eklenmiyor — kullanıcı bunu hiç göremez."
    )


def test_generate_stage_marks_ok_when_crag_ran_without_failure():
    ctx = _make_ctx(candidates=[])
    ctx.crag_verdict = "SUFFICIENT"
    ctx.crag_evaluator_failed = False

    ctx = GenerateStage(enabled=True).run(ctx)

    assert ctx.answer["crag_status"] == "OK"
    assert "SONUÇ DOĞRULANAMADI" not in ctx.answer["answer"]
