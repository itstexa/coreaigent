"""Offline Turkish hybrid retrieval adapted from mevzuat-rag's RRF core.

The standalone project uses Qdrant sparse vectors for large corpora.  This
workflow owns a small, repository-pinned corpus already embedded per request,
so the same dense + lexical rank fusion stays local and dependency-free.
"""

from __future__ import annotations

import math
import re

_TOKEN_RE = re.compile(r"[a-zçğıöşü0-9]+")
_STOPWORDS = frozenset({"ve", "veya", "ile", "için", "bir", "bu", "şu", "da", "de", "mi", "mı", "mu", "mü", "olan", "olarak", "sayılı", "kanun", "kanunu", "madde", "maddesi", "kapsamında"})


def tokenize_tr(text):
    lowered = (text or "").replace("I", "ı").replace("İ", "i").lower()
    return [token for token in _TOKEN_RE.findall(lowered) if len(token) > 1 and token not in _STOPWORDS]


def bm25_scores(query, documents, *, k1=1.2, b=0.75):
    """Small-corpus BM25; output is normalized solely for the safety gate."""
    terms = tokenize_tr(query)
    tokenized = [tokenize_tr(document) for document in documents]
    if not terms or not tokenized:
        return [0.0] * len(tokenized)
    count = len(tokenized)
    average = sum(len(tokens) for tokens in tokenized) / count or 1.0
    frequencies = {term: sum(term in tokens for tokens in tokenized) for term in set(terms)}
    raw = []
    for tokens in tokenized:
        score = 0.0
        for term in terms:
            df = frequencies.get(term, 0)
            if not df:
                continue
            tf = tokens.count(term)
            idf = math.log(1 + (count - df + 0.5) / (df + 0.5))
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * len(tokens) / average))
        raw.append(score)
    maximum = max(raw, default=0.0)
    return [value / maximum if maximum else 0.0 for value in raw]


def reciprocal_rank_fusion(ranked_ids, *, k=60):
    scores = {}
    for identifiers in ranked_ids:
        for rank, identifier in enumerate(identifiers, start=1):
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (k + rank)
    return scores


def fuse_chunks(chunks, dense_scores, query):
    """Attach dense, lexical and RRF rank scores without changing source IDs."""
    lexical_scores = bm25_scores(query, [chunk["content"] for chunk in chunks])
    dense_order = [chunk["chunk_id"] for chunk, _score in sorted(zip(chunks, dense_scores), key=lambda item: (-item[1], item[0]["chunk_id"]))]
    lexical_order = [chunk["chunk_id"] for chunk, score in sorted(zip(chunks, lexical_scores), key=lambda item: (-item[1], item[0]["chunk_id"])) if score > 0]
    fused = reciprocal_rank_fusion([dense_order, lexical_order])
    result = []
    for chunk, dense, lexical in zip(chunks, dense_scores, lexical_scores):
        item = dict(chunk)
        item["dense_score"] = float(dense)
        item["lexical_score"] = float(lexical)
        item["rank_score"] = float(fused.get(item["chunk_id"], 0.0))
        # Existing contracts call this field score.  Its dense meaning remains
        # stable; rank_score only decides the order among eligible citations.
        item["score"] = float(dense)
        result.append(item)
    return result
