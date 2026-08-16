"""Environment-driven configuration for the RAG service."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RAGConfig:
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

    @classmethod
    def from_env(cls) -> "RAGConfig":
        return cls(
            qdrant_url=os.environ.get("QDRANT_URL") or None,
            qdrant_local_path=os.environ.get("QDRANT_LOCAL_PATH", "./data/qdrant_local"),
            qdrant_collection=os.environ.get("QDRANT_COLLECTION_MEVZUAT", "mevzuat_chunks"),
            embedding_model=os.environ.get("RAG_EMBEDDING_MODEL", "BAAI/bge-m3"),
            embedding_device=os.environ.get("RAG_EMBEDDING_DEVICE", "cpu"),
            chunk_max_tokens=int(os.environ.get("RAG_CHUNK_MAX_TOKENS", "768")),
            chunk_overlap_tokens=int(os.environ.get("RAG_CHUNK_OVERLAP_TOKENS", "80")),
            retrieval_top_k=int(os.environ.get("RAG_RETRIEVAL_TOP_K", "5")),
            resmi_gazete_rss_url=os.environ.get("RESMI_GAZETE_RSS_URL", "https://www.resmigazete.gov.tr/rss"),
            jina_reader_base_url=os.environ.get("AGENT_REACH_JINA_READER_BASE_URL", "https://r.jina.ai"),
        )
