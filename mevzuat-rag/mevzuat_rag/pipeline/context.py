"""PipelineContext — the state threaded through every retrieval pipeline
stage, and TraceEntry — the per-stage observability record the Pipeline
runner appends to on every stage (see runner.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mevzuat_rag.config import RAGConfig
from mevzuat_rag.pipeline.candidate import Candidate

if TYPE_CHECKING:
    from mevzuat_rag.engine import RAGEngine


@dataclass
class TraceEntry:
    stage: str
    input_count: int
    output_count: int
    duration_ms: float
    extra: dict = field(default_factory=dict)


@dataclass
class PipelineContext:
    original_query: str
    engine: "RAGEngine"
    top_k: int
    debug: bool = False

    # [Dinamik VRAM Profili] Bu İSTEĞE ÖZEL, salt-okunur RAGConfig kopyası —
    # dynamic_profile.apply_dynamic_profile() tarafından RAGEngine.config'ten
    # MUTATE ETMEDEN üretilir (bkz. dynamic_profile.py modül docstring'i:
    # aynı RAGEngine'i eşzamanlı sorgulayan farklı isteklerin birbirinin
    # config'ini ezmemesi için). hybrid/rerank/multi_query/hyde/parent_doc/
    # crag stage'leri ctx.engine.config yerine ctx.effective_config okur.
    # None kalamaz — RAGEngine._run() her zaman set eder.
    effective_config: RAGConfig | None = None
    dynamic_profile: str | None = None

    @property
    def resolved_config(self) -> RAGConfig:
        """``effective_config`` set edilmemişse (ör. testlerde doğrudan
        ``PipelineContext(...)`` kurulumu, RAGEngine._run() dışından
        çağrılan eski kod yolları) ``engine.config``'e güvenle geri düşer —
        eski (dinamik profil öncesi) davranışla birebir aynı sonucu verir."""
        return self.effective_config or self.engine.config

    # [0] Self-RAG router decision: {"decision": ..., "confidence": ..., "reason": ...}
    decision: dict | None = None
    # [1] Multi-Query / HyDE outputs
    generated_queries: list[str] = field(default_factory=list)
    hyde_answer: str | None = None
    # [2]-[6] retrieval/rerank/expand/compress working set
    candidates: list[Candidate] = field(default_factory=list)
    # [5] CRAG loop state
    crag_verdict: str | None = None  # "SUFFICIENT" | "PARTIAL" | "INSUFFICIENT"
    crag_loop_count: int = 0
    # True iff the CRAG evaluator LLM call itself raised (network/auth/timeout/
    # malformed JSON) at least once — CRAG fails OPEN in that case (proceeds
    # with whatever candidates it already has), so this is the only signal
    # that the "SUFFICIENT" verdict wasn't actually judged by anything. See
    # GenerateStage, which surfaces this to the caller instead of staying
    # silent about it (bkz. denetim bulgusu: "CRAG fail-open onaysız").
    crag_evaluator_failed: bool = False
    crag_failure_reason: str | None = None
    # [7] Generate output: {"answer": str, "citations": [...], "sources": [...]}
    answer: dict | None = None
    # [10] Semantic Cache: True iff SemanticCacheCheckStage populated ``answer``
    # from a past cached query instead of a fresh GenerateStage call. Read by
    # SemanticCacheStoreStage to avoid re-storing an answer that was already
    # in the cache (storing it again would just re-embed the paraphrase that
    # triggered the hit, not the original stored query).
    answer_from_cache: bool = False

    # short-circuit: e.g. router said ANSWER_DIRECTLY/CLARIFY, skip retrieval
    stopped: bool = False
    stopped_reason: str | None = None

    trace: list[TraceEntry] = field(default_factory=list)
