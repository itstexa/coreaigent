"""[2] Rank fusion for Hybrid Retrieve — RRF (default) or weighted score
fusion, both keyed by chunk_id so dense and BM25 hits for the same chunk
merge into one entry instead of appearing twice.
"""
from __future__ import annotations


def reciprocal_rank_fusion(ranked_id_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """RRF: score(id) = sum over lists of 1 / (k + rank), rank 1-indexed."""
    scores: dict[str, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, chunk_id in enumerate(ranked_ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def _min_max_normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi == lo:
        return {chunk_id: 1.0 for chunk_id in scores}
    return {chunk_id: (v - lo) / (hi - lo) for chunk_id, v in scores.items()}


def weighted_fusion(dense_scores: dict[str, float], bm25_scores: dict[str, float], alpha: float) -> dict[str, float]:
    """alpha=1.0 => pure dense/vector, alpha=0.0 => pure BM25. Both inputs
    are min-max normalized to [0, 1] first so the two scales are comparable
    before combining."""
    dense_norm = _min_max_normalize(dense_scores)
    bm25_norm = _min_max_normalize(bm25_scores)
    ids = set(dense_norm) | set(bm25_norm)
    return {
        chunk_id: alpha * dense_norm.get(chunk_id, 0.0) + (1 - alpha) * bm25_norm.get(chunk_id, 0.0)
        for chunk_id in ids
    }
