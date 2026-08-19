"""Environment-driven, profile-layered configuration for the RAG service.

Priority: env var (legacy flat names below, unchanged from before this
layer existed) > profile YAML (config/{profile}.yaml) > default YAML
(config/default.yaml). Profile is selected via RAG_PROFILE env var
(default: "default").

RAGConfig.from_env() is kept as an alias for RAGConfig.load() — existing
call sites (engine.py, ingest_pipeline.py, tests) are unaffected.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from mevzuat_rag.device import resolve_device

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data"))


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _layered_yaml(profile: str) -> dict:
    default = _load_yaml(CONFIG_DIR / "default.yaml")
    if profile == "default":
        return default
    override = _load_yaml(CONFIG_DIR / f"{profile}.yaml")
    return _deep_merge(default, override)


def _resolve_local_path(raw: str) -> str:
    """Relative paths resolve against DATA_DIR's parent (PROJECT_ROOT by
    default), never against the process cwd — so behavior doesn't change
    depending on where a script happens to be invoked from."""
    path = Path(raw)
    if path.is_absolute():
        return str(path)
    return str((PROJECT_ROOT / raw).resolve())


@dataclass
class StageToggle:
    enabled: bool = False


@dataclass
class RouterConfig(StageToggle):
    model: str = "deepseek-chat"


@dataclass
class HybridConfig(StageToggle):
    dense_top_k: int = 20
    bm25_top_k: int = 20
    fusion: str = "rrf"
    rrf_k: int = 60
    alpha: float = 1.0


@dataclass
class RerankConfig(StageToggle):
    backend: str = "cross_encoder"
    model: str = "BAAI/bge-reranker-v2-m3"
    top_n: int = 5
    min_score: float = 0.0


@dataclass
class MultiQueryConfig(StageToggle):
    n_queries: int = 4
    prompt_path: str = "prompts/multi_query.txt"


@dataclass
class HyDEConfig(StageToggle):
    trigger_max_tokens: int = 12
    max_answer_tokens: int = 150


@dataclass
class ParentDocConfig(StageToggle):
    token_budget_fraction: float = 0.6
    context_window_tokens: int = 8000


@dataclass
class CompressionConfig(StageToggle):
    token_budget: int = 2000
    dedup_cosine_threshold: float = 0.95
    llm_summarize: bool = False


@dataclass
class CRAGConfig(StageToggle):
    max_loops: int = 2
    insufficient_strategy: str = "force_hyde"


@dataclass
class GenerationConfig:
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"
    temperature: float = 0.0
    max_tokens: int = 800
    timeout_s: float = 30.0
    retry_attempts: int = 2
    retry_backoff_s: float = 1.0


@dataclass
class RAGConfig:
    # --- legacy flat fields — names/semantics unchanged from before the
    # YAML/profile layer existed, so existing code and tests keep working. ---
    qdrant_url: str | None
    qdrant_local_path: str
    qdrant_collection: str
    embedding_model: str
    embedding_device: str
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    retrieval_top_k: int
    resmi_gazete_rss_url: str
    jina_reader_base_url: str

    # --- portability ---
    device: str = "cpu"
    profile: str = "default"

    # --- stage toggles (all default to disabled; flipped on per checkpoint) ---
    router: RouterConfig = field(default_factory=RouterConfig)
    hybrid: HybridConfig = field(default_factory=HybridConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    multi_query: MultiQueryConfig = field(default_factory=MultiQueryConfig)
    hyde: HyDEConfig = field(default_factory=HyDEConfig)
    parent_doc: ParentDocConfig = field(default_factory=ParentDocConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    crag: CRAGConfig = field(default_factory=CRAGConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)

    debug: bool = False

    @classmethod
    def load(cls, profile: str | None = None) -> "RAGConfig":
        profile = profile or os.environ.get("RAG_PROFILE", "default")
        y = _layered_yaml(profile)

        device = os.environ.get("DEVICE") or y.get("device", "auto")
        if device == "auto":
            device = resolve_device()

        qdrant = y.get("qdrant", {}) or {}
        embedding = y.get("embedding", {}) or {}
        chunking = y.get("chunking", {}) or {}
        retrieval = y.get("retrieval", {}) or {}
        ingestion = y.get("ingestion", {}) or {}

        local_path = os.environ.get("QDRANT_LOCAL_PATH", qdrant.get("local_path", "./data/qdrant_local"))

        gen = y.get("generation", {}) or {}
        gen_retry = gen.get("retry", {}) or {}

        return cls(
            qdrant_url=os.environ.get("QDRANT_URL") or qdrant.get("url") or None,
            qdrant_local_path=_resolve_local_path(local_path),
            qdrant_collection=os.environ.get("QDRANT_COLLECTION_MEVZUAT", qdrant.get("collection", "mevzuat_chunks")),
            embedding_model=os.environ.get("RAG_EMBEDDING_MODEL", embedding.get("model", "BAAI/bge-m3")),
            embedding_device=os.environ.get("RAG_EMBEDDING_DEVICE") or device,
            chunk_max_tokens=int(os.environ.get("RAG_CHUNK_MAX_TOKENS", chunking.get("max_tokens", 768))),
            chunk_overlap_tokens=int(os.environ.get("RAG_CHUNK_OVERLAP_TOKENS", chunking.get("overlap_tokens", 80))),
            retrieval_top_k=int(os.environ.get("RAG_RETRIEVAL_TOP_K", retrieval.get("top_k", 5))),
            resmi_gazete_rss_url=os.environ.get("RESMI_GAZETE_RSS_URL", ingestion.get("resmi_gazete_rss_url", "https://www.resmigazete.gov.tr/rss")),
            jina_reader_base_url=os.environ.get("AGENT_REACH_JINA_READER_BASE_URL", ingestion.get("jina_reader_base_url", "https://r.jina.ai")),
            device=device,
            profile=profile,
            router=RouterConfig(**(y.get("router", {}) or {})),
            hybrid=HybridConfig(**(y.get("hybrid", {}) or {})),
            rerank=RerankConfig(**(y.get("rerank", {}) or {})),
            multi_query=MultiQueryConfig(**(y.get("multi_query", {}) or {})),
            hyde=HyDEConfig(**(y.get("hyde", {}) or {})),
            parent_doc=ParentDocConfig(**(y.get("parent_doc", {}) or {})),
            compression=CompressionConfig(**(y.get("compression", {}) or {})),
            crag=CRAGConfig(**(y.get("crag", {}) or {})),
            generation=GenerationConfig(
                provider=gen.get("provider", "deepseek"),
                model=os.environ.get("DEEPSEEK_MODEL", gen.get("model", "deepseek-chat")),
                base_url=os.environ.get("DEEPSEEK_BASE_URL", gen.get("base_url", "https://api.deepseek.com/v1")),
                temperature=float(gen.get("temperature", 0.0)),
                max_tokens=int(gen.get("max_tokens", 800)),
                timeout_s=float(gen.get("timeout_s", 30)),
                retry_attempts=int(gen_retry.get("attempts", 2)),
                retry_backoff_s=float(gen_retry.get("backoff_base_s", 1.0)),
            ),
            debug=_bool_env("RAG_DEBUG", bool((y.get("observability", {}) or {}).get("debug", False))),
        )

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Backward-compatible alias — existing code calls this directly."""
        return cls.load()
