"""Dense embedding wrapper — deliberately the same pattern as
``insangram/src/rag/embed.py``: plain ``sentence-transformers`` BGE-M3,
dense-only, cosine similarity. No sparse vectors, no reranker — that stack is
already proven to work and isn't being changed for this service.
"""
from __future__ import annotations

from sentence_transformers import SentenceTransformer

_model_cache: dict[str, SentenceTransformer] = {}


def get_embedder(model_name: str, device: str) -> SentenceTransformer:
    key = f"{model_name}::{device}"
    if key not in _model_cache:
        _model_cache[key] = SentenceTransformer(model_name, device=device)
    return _model_cache[key]


def embed_texts(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors = model.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vectors]


def embed_query(model: SentenceTransformer, query: str) -> list[float]:
    return model.encode(query, normalize_embeddings=True).tolist()
