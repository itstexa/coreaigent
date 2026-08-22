"""[10] min_score eşiği testleri.

Eşik değeri (0.05) 2026-08-22'de golden set + corpus-dışı sorularla
kalibre edildi (bkz. config.py'deki RerankConfig.min_score yorumu):
corpus-içi en zayıf soru 0.5306, corpus-dışı en güçlü "yanlış pozitif"
0.0006 skor aldı — aralarında ~800x fark var, 0.05 ikisi arasında güvenli
bir sınır.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from mevzuat_rag.generation import generate_answer
from mevzuat_rag.pipeline.candidate import Candidate
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.pipeline.stages.rerank import RerankStage


def _fake_candidate(cid: str) -> Candidate:
    chunk = MagicMock()
    chunk.text = f"metin-{cid}"
    chunk.citation = f"kaynak-{cid}"
    return Candidate(id=cid, text=f"metin-{cid}", score=0.0, source="fused", parent_id=None, chunk=chunk)


def _make_ctx(n_candidates: int) -> PipelineContext:
    engine = MagicMock()
    engine.config.rerank.model = "fake-model"
    engine.config.rerank.min_score = 0.05
    # MagicMock'un auto-vivify'ı yüzünden açıkça set edilmezse
    # engine.config.rerank.adaptive_cutoff, rerank.py'nin
    # getattr(config, "adaptive_cutoff", False) kontrolünde HER ZAMAN
    # truthy bir Mock döner (gerçek RerankConfig'in varsayılanı False'tur) —
    # bu yüzden burada gerçek varsayılanla eşleşecek şekilde açıkça set ediliyor.
    engine.config.rerank.adaptive_cutoff = False
    engine.config.device = "cpu"
    ctx = PipelineContext(original_query="test sorgu", engine=engine, top_k=5)
    ctx.candidates = [_fake_candidate(str(i)) for i in range(n_candidates)]
    return ctx


@patch("mevzuat_rag.pipeline.stages.rerank._get_cross_encoder")
def test_below_threshold_candidates_are_dropped(mock_get_encoder):
    fake_model = MagicMock()
    # 3 aday: biri yüksek (0.9, golden-set aralığında), ikisi eşiğin altında
    # (0.0006 ve 0.02 — corpus-dışı gürültü skorlarına yakın).
    fake_model.predict.return_value = [0.9, 0.0006, 0.02]
    mock_get_encoder.return_value = fake_model

    ctx = _make_ctx(3)
    result = RerankStage(enabled=True).run(ctx)

    assert len(result.candidates) == 1
    assert result.candidates[0].id == "0"
    assert result.candidates[0].score == 0.9


@patch("mevzuat_rag.pipeline.stages.rerank._get_cross_encoder")
def test_all_below_threshold_yields_empty_candidates_not_crash(mock_get_encoder):
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.0001, 0.0002, 0.0]
    mock_get_encoder.return_value = fake_model

    ctx = _make_ctx(3)
    result = RerankStage(enabled=True).run(ctx)

    assert result.candidates == []


def test_empty_candidates_after_min_score_leads_to_builtin_refusal_not_llm_call():
    """generate_answer([]) hiç DeepSeek çağrısı yapmadan doğrudan reddediyor —
    min_score her şeyi eledikten sonra akışın güvenli bittiğini kanıtlar."""
    result = generate_answer("herhangi bir soru", chunks=[])
    assert result["answer"] == "Verilen mevzuat parçalarında bu sorunun cevabı yok."
    assert result["citations"] == []


def test_default_config_min_score_is_calibrated_not_inert():
    from mevzuat_rag.config import RAGConfig

    config = RAGConfig.from_env()
    assert config.rerank.min_score > 0.0, (
        "min_score 0.0 ise fiilen hiçbir şeyi filtrelemez (NOTES.md'de "
        "'Score threshold yok' diye işaretlenen boşluk budur)"
    )
    assert config.rerank.min_score < 0.5306, "golden set'teki en zayıf gerçek eşleşmeyi elemeyecek kadar düşük olmalı"
