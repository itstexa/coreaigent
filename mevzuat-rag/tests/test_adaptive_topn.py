"""[Retrieval #2] Adaptif rerank kesimi testleri (docs/IMPROVEMENT_IDEAS.md).

rerank.py'deki sabit ``top_n`` kesiminin yerine, ``config.adaptive_cutoff``
açıkken skor dizisindeki ani orantısal düşüşe (elbow/gap) göre kesim
yapıldığını kanıtlar. min_score (0.05) tabanı zaten devrede — burada test
edilen yalnızca üst kesim mantığı.

Bu dosya test_min_score.py'deki mock cross-encoder desenini izler: gerçek
model yüklenmez, ``_get_cross_encoder`` patch'lenir.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from mevzuat_rag.pipeline.candidate import Candidate
from mevzuat_rag.pipeline.context import PipelineContext
from mevzuat_rag.pipeline.stages.rerank import RerankStage, _adaptive_cutoff_count


def _fake_candidate(cid: str) -> Candidate:
    chunk = MagicMock()
    chunk.text = f"metin-{cid}"
    chunk.citation = f"kaynak-{cid}"
    return Candidate(id=cid, text=f"metin-{cid}", score=0.0, source="fused", parent_id=None, chunk=chunk)


def _make_ctx(n_candidates: int, *, top_n: int = 5, min_score: float = 0.05,
              adaptive_cutoff: bool = False, adaptive_drop_ratio: float = 0.5) -> PipelineContext:
    engine = MagicMock()
    engine.config.rerank.model = "fake-model"
    engine.config.rerank.min_score = min_score
    engine.config.rerank.top_n = top_n
    engine.config.rerank.adaptive_cutoff = adaptive_cutoff
    engine.config.rerank.adaptive_drop_ratio = adaptive_drop_ratio
    engine.config.device = "cpu"
    ctx = PipelineContext(original_query="test sorgu", engine=engine, top_k=5)
    ctx.candidates = [_fake_candidate(str(i)) for i in range(n_candidates)]
    return ctx


# --- birim testleri: _adaptive_cutoff_count doğrudan --------------------

def test_adaptive_cutoff_count_finds_sharp_drop():
    # [0.9, 0.85, 0.15, 0.1] -> 0.85'ten 0.15'e oran 0.176 < 0.5, i=2'de kes.
    assert _adaptive_cutoff_count([0.9, 0.85, 0.15, 0.1], top_n=5, drop_ratio=0.5) == 2


def test_adaptive_cutoff_count_never_returns_zero():
    assert _adaptive_cutoff_count([0.9, 0.85, 0.8, 0.75], top_n=5, drop_ratio=0.9999) >= 1
    assert _adaptive_cutoff_count([0.01], top_n=5, drop_ratio=0.5) == 1


def test_adaptive_cutoff_count_caps_at_top_n_times_1_5():
    # Yumuşak/gradual düşüş, hiçbir yerde büyük gap yok -> pencere sınırına
    # (top_n*1.5 = 7 için ceil(7.5)=8) kadar taşabilir ama daha fazlasına asla.
    gradual = [0.9 - i * 0.02 for i in range(20)]
    keep = _adaptive_cutoff_count(gradual, top_n=5, drop_ratio=0.5)
    assert keep <= 8  # ceil(5 * 1.5)
    assert keep >= 1


def test_adaptive_cutoff_count_can_keep_more_than_top_n_on_soft_decline():
    # İlk 7 skor yumuşak düşüyor, sonra sert bir uçurum var (0.65 -> 0.05).
    # top_n=5 ama gerçek "elbow" 7'de -> 7 tutulmalı (cap: ceil(5*1.5)=8).
    soft_then_cliff = [0.85, 0.82, 0.79, 0.75, 0.72, 0.68, 0.65, 0.05, 0.03]
    keep = _adaptive_cutoff_count(soft_then_cliff, top_n=5, drop_ratio=0.5)
    assert keep == 7


def test_adaptive_cutoff_count_empty_scores_returns_zero():
    assert _adaptive_cutoff_count([], top_n=5, drop_ratio=0.5) == 0


# --- entegrasyon testleri: RerankStage.run üzerinden ---------------------

@patch("mevzuat_rag.pipeline.stages.rerank._get_cross_encoder")
def test_adaptive_cutoff_true_narrows_below_top_n_on_sharp_drop(mock_get_encoder):
    """Dar/keskin düşüş: tek net cevap senaryosu — top_n=5 olsa da yalnızca
    ilk 2 aday (gap öncesi) tutulmalı."""
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.9, 0.85, 0.15, 0.1, 0.06]
    mock_get_encoder.return_value = fake_model

    ctx = _make_ctx(5, top_n=5, adaptive_cutoff=True, adaptive_drop_ratio=0.5)
    result = RerankStage(enabled=True).run(ctx)

    assert len(result.candidates) == 2
    assert [c.id for c in result.candidates] == ["0", "1"]


@patch("mevzuat_rag.pipeline.stages.rerank._get_cross_encoder")
def test_adaptive_cutoff_true_can_keep_more_than_top_n_on_soft_decline(mock_get_encoder):
    """Geniş/yumuşak düşüş: birden fazla alakalı madde senaryosu — top_n=5
    olsa da elbow 7'de olduğundan (cap 8 içinde) 7 aday tutulmalı."""
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.85, 0.82, 0.79, 0.75, 0.72, 0.68, 0.65, 0.05, 0.03]
    mock_get_encoder.return_value = fake_model

    ctx = _make_ctx(9, top_n=5, adaptive_cutoff=True, adaptive_drop_ratio=0.5)
    result = RerankStage(enabled=True).run(ctx)

    assert len(result.candidates) == 7


@patch("mevzuat_rag.pipeline.stages.rerank._get_cross_encoder")
def test_adaptive_cutoff_true_never_drops_all_candidates(mock_get_encoder):
    """En az 1 aday her zaman kalmalı — hepsi elenmemeli (min_score'u geçen
    en az bir aday varsa)."""
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.9, 0.05, 0.05, 0.05]
    mock_get_encoder.return_value = fake_model

    ctx = _make_ctx(4, top_n=5, min_score=0.05, adaptive_cutoff=True, adaptive_drop_ratio=0.5)
    result = RerankStage(enabled=True).run(ctx)

    assert len(result.candidates) >= 1


@patch("mevzuat_rag.pipeline.stages.rerank._get_cross_encoder")
def test_adaptive_cutoff_true_respects_upper_cap(mock_get_encoder):
    """Hiç net gap olmayan uzun bir kuyrukta bile top_n * 1.5'i aşmamalı
    (sonsuz büyüme önlenir)."""
    fake_model = MagicMock()
    scores = [0.9 - i * 0.01 for i in range(30)]  # hepsi min_score üstünde, çok yumuşak düşüş
    fake_model.predict.return_value = scores
    mock_get_encoder.return_value = fake_model

    ctx = _make_ctx(30, top_n=5, min_score=0.05, adaptive_cutoff=True, adaptive_drop_ratio=0.5)
    result = RerankStage(enabled=True).run(ctx)

    assert len(result.candidates) <= 8  # ceil(5 * 1.5)


# --- regresyon: adaptive_cutoff=False (varsayılan) davranış değişmemeli --

@patch("mevzuat_rag.pipeline.stages.rerank._get_cross_encoder")
def test_adaptive_cutoff_false_keeps_fixed_top_n_behavior_sharp_drop(mock_get_encoder):
    """Varsayılan (adaptive_cutoff=False) iken, keskin düşüş olan aynı skor
    dizisinde bile sabit top_n=5 kesimi aynen uygulanmalı — davranış
    değişmemeli."""
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.9, 0.85, 0.15, 0.1, 0.06]
    mock_get_encoder.return_value = fake_model

    ctx = _make_ctx(5, top_n=5, adaptive_cutoff=False)
    result = RerankStage(enabled=True).run(ctx)

    # min_score=0.05 hepsini geçiyor, sabit top_n=5 -> 5 aday (adaptif kesim yok)
    assert len(result.candidates) == 5
    assert [c.id for c in result.candidates] == ["0", "1", "2", "3", "4"]


@patch("mevzuat_rag.pipeline.stages.rerank._get_cross_encoder")
def test_adaptive_cutoff_false_keeps_fixed_top_n_behavior_soft_decline(mock_get_encoder):
    """Varsayılan iken, yumuşak düşüşte bile top_n=5'ten fazla aday asla
    dönmemeli (adaptive_cutoff kapalıyken elbow mantığı hiç devreye girmez)."""
    fake_model = MagicMock()
    fake_model.predict.return_value = [0.85, 0.82, 0.79, 0.75, 0.72, 0.68, 0.65, 0.05, 0.03]
    mock_get_encoder.return_value = fake_model

    ctx = _make_ctx(9, top_n=5, adaptive_cutoff=False)
    result = RerankStage(enabled=True).run(ctx)

    assert len(result.candidates) == 5
    assert [c.id for c in result.candidates] == ["0", "1", "2", "3", "4"]


def test_default_config_adaptive_cutoff_is_off():
    """config/default.yaml + RerankConfig varsayılanı adaptive_cutoff=False
    olmalı — bu depodaki disiplinle tutarlı (yeni davranışlar doğrulanana
    kadar varsayılan kapalı)."""
    from mevzuat_rag.config import RAGConfig

    config = RAGConfig.from_env()
    assert config.rerank.adaptive_cutoff is False
