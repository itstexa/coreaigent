"""[10] Semantic Cache — caches DeepSeek-generated answers by the SEMANTIC
similarity of the query (cosine similarity of its bge-m3 embedding), not
exact string match. Government offices ask the same handful of questions
over and over in slightly different wording ("doğum izni kaç gün?",
"doğum izni kaç gün sürüyor?") — this cuts DeepSeek API cost/latency for the
paraphrase, not just the literal repeat.

Two stages, wired into RAGEngine._build_pipeline only in the want_answer=True
branch (see engine.py):

- SemanticCacheCheckStage: FIRST in the pipeline, before RouterStage. On a
  hit it sets ctx.answer to a dict in the exact shape GenerateStage produces
  (see generate.py) and sets ctx.stopped = True, which short-circuits every
  downstream stage per the standard Stage protocol (see runner.py) — retrieval,
  rerank, and the DeepSeek generation call are all skipped. This is where the
  cost/latency savings come from.
- SemanticCacheStoreStage: LAST, after PostHocVerifyStage. Writes the query
  embedding + final (already-verified) answer to the cache collection, but
  only for an answer that did NOT itself come from the cache (see
  ctx.answer_from_cache in pipeline/context.py) — otherwise a paraphrase that
  hit the cache would re-embed itself as a second, redundant cache entry.

Storage: reuses the SAME embedded Qdrant client the engine already opens
(``ctx.engine.store.client``) with a NEW collection (default: "semantic_cache")
— never a second QdrantClient/QdrantStore pointed at the same local_path.
Embedded Qdrant holds an on-disk lock per client instance; two separate
QdrantClient objects on the same local_path collide/deadlock (see store.py's
module docstring and RAGEngine.store's ``_store_lock`` comment). Accessing
``ctx.engine.store`` here is what actually constructs that one client (lazily,
lock-guarded) if no earlier stage has touched it yet.

Embedding: reuses ``ctx.engine.model`` (the already-loaded SentenceTransformer)
and the existing ``embed_texts_with_config`` helper (embedding.py) — no
second embedding model instance is loaded.

Both stages fail open: if the cache check/write raises (Qdrant error,
embedding error, ...), a WARNING is logged and the pipeline proceeds as if
the cache stage were disabled — a caching optimization must never be able to
break answering a question, same "fails open" policy CRAG/post_hoc_verify use
for their own LLM-call failures.
"""
from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime, timezone

from qdrant_client.models import Distance, PointStruct, VectorParams

from mevzuat_rag.embedding import embed_texts_with_config
from mevzuat_rag.pipeline.context import PipelineContext

logger = logging.getLogger("mevzuat_rag.semantic_cache")


def _ensure_cache_collection(client, collection: str, dim: int) -> None:
    """Creates ``collection`` on the shared client if it doesn't exist yet.
    Uses the same client the engine's main ``mevzuat_chunks`` collection lives
    on (``ctx.engine.store.client``) — see module docstring for why a second
    client must never be opened."""
    names = [c.name for c in client.get_collections().collections]
    if collection not in names:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def _embed_query(ctx: PipelineContext) -> list[float]:
    vectors = embed_texts_with_config(
        ctx.engine.model,
        [ctx.original_query],
        config=ctx.engine.config.embedding,
    )
    return vectors[0]


class SemanticCacheCheckStage:
    name = "semantic_cache_check"

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        config = ctx.engine.config.semantic_cache
        try:
            client = ctx.engine.store.client
            _ensure_cache_collection(client, config.collection, ctx.engine.config.embedding_dim)
            query_vector = _embed_query(ctx)
            hits = client.query_points(
                collection_name=config.collection,
                query=query_vector,
                limit=1,
                with_payload=True,
            ).points
        except Exception as exc:
            logger.warning("Semantic cache kontrolü başarısız (%s) — normal akışa devam ediliyor (fails open).", exc)
            return ctx

        if not hits or hits[0].score < config.similarity_threshold:
            return ctx

        hit = hits[0]
        cached_answer = hit.payload.get("answer")
        if not cached_answer:
            return ctx

        logger.info(
            "Semantic cache HIT (score=%.4f, eşik=%.4f) — sorgu: %r, önbellekteki sorgu: %r",
            hit.score, config.similarity_threshold, ctx.original_query, hit.payload.get("query"),
        )

        ctx.answer = copy.deepcopy(cached_answer)
        ctx.answer_from_cache = True
        ctx.stopped = True
        ctx.stopped_reason = "semantic_cache:hit"
        return ctx


class SemanticCacheStoreStage:
    name = "semantic_cache_store"

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.answer_from_cache:
            return ctx  # already in the cache under its own original query — don't re-store
        if ctx.answer is None or not ctx.answer.get("answer"):
            return ctx  # nothing usable to cache (e.g. generation failed upstream)

        config = ctx.engine.config.semantic_cache
        try:
            client = ctx.engine.store.client
            _ensure_cache_collection(client, config.collection, ctx.engine.config.embedding_dim)
            query_vector = _embed_query(ctx)
            client.upsert(
                collection_name=config.collection,
                points=[
                    PointStruct(
                        id=str(uuid.uuid4()),
                        vector=query_vector,
                        payload={
                            "query": ctx.original_query,
                            "answer": ctx.answer,
                            "cached_at": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                ],
            )
        except Exception as exc:
            logger.warning("Semantic cache yazımı başarısız (%s) — cevap kullanıcıya normal döner, sadece önbelleğe alınamadı.", exc)

        return ctx
