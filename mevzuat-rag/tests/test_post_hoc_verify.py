"""[8] Hakem Ajan (Critic Agent) testleri.

Yapısal kontrol testleri gerçek/LLM'siz (her zaman doğru sonuç verir).
LLM tabanlı Hakem Ajan kontrolü mock'lu.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.pipeline.stages.post_hoc_verify import (
    HAKEM_BLOCKED_TEXT,
    REFUSAL_TEXT,
    PostHocVerifyStage,
    _structural_check,
    verify_answer,
)


def _fake_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


def _make_ctx(answer_text: str, n_sources: int, llm_check: bool = True) -> PipelineContext:
    engine = MagicMock()
    engine.config.post_hoc_verify.llm_check = llm_check
    engine.config.post_hoc_verify.model = "deepseek-chat"
    ctx = PipelineContext(original_query="test sorgu", engine=engine, top_k=5)
    ctx.answer = {
        "answer": answer_text,
        "citations": [f"kaynak-{i}" for i in range(1, n_sources + 1)],
        "sources": [{"citation": f"kaynak-{i}", "score": 0.9, "text": f"metin-{i}"} for i in range(1, n_sources + 1)],
    }
    return ctx


def test_structural_check_flags_out_of_range_citation():
    assert _structural_check("Cevap [1] ve [4]'e göre doğrudur.", n_sources=3) == [4]


def test_structural_check_passes_valid_citations():
    assert _structural_check("Cevap [1] ve [2]'ye göre doğrudur.", n_sources=3) == []


def test_structural_check_flags_zero_index():
    assert _structural_check("Cevap [0]'a göre doğrudur.", n_sources=3) == [0]


def test_stage_rejects_out_of_range_citation_without_calling_llm():
    ctx = _make_ctx("Cevap [1] ve [7]'ye göre doğrudur.", n_sources=3)
    with patch("mevzuat_rag.pipeline.stages.post_hoc_verify.get_client") as mock_get_client:
        result = PostHocVerifyStage(enabled=True).run(ctx)
        mock_get_client.assert_not_called()  # yapısal hata varken LLM çağrısı gereksiz maliyet

    assert result.answer["answer"] == HAKEM_BLOCKED_TEXT
    assert result.answer["citations"] == []
    assert result.answer["post_hoc_verdict"] == "STRUCTURAL_FAIL"


@patch("mevzuat_rag.pipeline.stages.post_hoc_verify.get_client")
def test_stage_keeps_answer_on_valid_verdict(mock_get_client):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_response(
        json.dumps({"is_valid": True, "reason": "kaynakla uyumlu"})
    )
    mock_get_client.return_value = fake_client

    ctx = _make_ctx("Cevap [1]'e göre doğrudur.", n_sources=1)
    result = PostHocVerifyStage(enabled=True).run(ctx)

    assert result.answer["answer"] == "Cevap [1]'e göre doğrudur."
    assert result.answer["post_hoc_verdict"] == "VALID"


@patch("mevzuat_rag.pipeline.stages.post_hoc_verify.get_client")
def test_stage_blocks_answer_on_invalid_verdict(mock_get_client):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_response(
        json.dumps({"is_valid": False, "reason": "kaynakta bu iddia yok — uydurma süre"})
    )
    mock_get_client.return_value = fake_client

    ctx = _make_ctx("Cevap [1]'e göre kesinlikle doğrudur.", n_sources=1)
    result = PostHocVerifyStage(enabled=True).run(ctx)

    assert result.answer["answer"] == HAKEM_BLOCKED_TEXT
    assert result.answer["citations"] == []
    assert result.answer["post_hoc_verdict"] == "REJECTED_BY_CRITIC"
    assert "uydurma" in result.answer["post_hoc_reason"]


@patch("mevzuat_rag.pipeline.stages.post_hoc_verify.get_client")
def test_llm_failure_fails_open_keeps_original_answer(mock_get_client):
    """CRAG'daki 'evaluator failure fails OPEN' politikasıyla aynı — altyapı
    sorunu sistemi daha kırılgan yapmamalı."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("401 invalid key")
    mock_get_client.return_value = fake_client

    ctx = _make_ctx("Cevap [1]'e göre doğrudur.", n_sources=1)
    result = PostHocVerifyStage(enabled=True).run(ctx)

    assert result.answer["answer"] == "Cevap [1]'e göre doğrudur."
    assert result.answer["post_hoc_verdict"] == "EVALUATOR_FAILED_OPEN"


def test_llm_check_false_skips_llm_entirely():
    ctx = _make_ctx("Cevap [1]'e göre doğrudur.", n_sources=1, llm_check=False)
    with patch("mevzuat_rag.pipeline.stages.post_hoc_verify.get_client") as mock_get_client:
        result = PostHocVerifyStage(enabled=True).run(ctx)
        mock_get_client.assert_not_called()

    assert result.answer["answer"] == "Cevap [1]'e göre doğrudur."
    assert result.answer["post_hoc_verdict"] == "STRUCTURAL_OK_UNCHECKED"


def test_already_refused_answer_is_not_reverified():
    ctx = _make_ctx(REFUSAL_TEXT, n_sources=0)
    with patch("mevzuat_rag.pipeline.stages.post_hoc_verify.get_client") as mock_get_client:
        result = PostHocVerifyStage(enabled=True).run(ctx)
        mock_get_client.assert_not_called()
    assert result.answer["answer"] == REFUSAL_TEXT


def test_already_blocked_answer_is_not_reverified():
    ctx = _make_ctx(HAKEM_BLOCKED_TEXT, n_sources=0)
    with patch("mevzuat_rag.pipeline.stages.post_hoc_verify.get_client") as mock_get_client:
        result = PostHocVerifyStage(enabled=True).run(ctx)
        mock_get_client.assert_not_called()
    assert result.answer["answer"] == HAKEM_BLOCKED_TEXT


def test_disabled_stage_does_not_run():
    ctx = _make_ctx("Cevap [1] ve [99]'a göre doğrudur.", n_sources=1)
    stage = PostHocVerifyStage(enabled=False)
    assert stage.enabled is False
    # Pipeline runner devre dışı stage'i hiç çağırmaz (bkz. runner.py) —
    # burada doğrudan .run() çağırmıyoruz, yalnızca enabled=False'ın
    # kaydedildiğini doğruluyoruz.


@patch("mevzuat_rag.pipeline.stages.post_hoc_verify.get_client")
def test_verify_answer_function_directly(mock_get_client):
    """verify_answer() pipeline dışında da doğrudan çağrılabilir (Hakem
    Ajan'ı elle test etmek için, bkz. scripts/test_hakem_agent.py)."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_response(
        json.dumps({"is_valid": False, "reason": "cevaptaki 90 günlük süre kaynakta yok"})
    )
    mock_get_client.return_value = fake_client

    result = verify_answer(
        "Başvurular 90 gün içinde sonuçlandırılır [1].",
        [{"citation": "3071 sayılı Kanun, Madde 8", "text": "Kurul, gönderilen dilekçeleri en geç altmış gün içinde cevaplandırır."}],
    )
    assert result == {"is_valid": False, "reason": "cevaptaki 90 günlük süre kaynakta yok"}
