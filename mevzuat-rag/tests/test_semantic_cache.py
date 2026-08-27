"""[10] Semantic Cache tests — real bge-m3 CPU embedding, real embedded
Qdrant (tempfile.TemporaryDirectory, same pattern as test_smoke_pipeline.py),
only the DeepSeek/LLM calls (router, generate, post_hoc_verify) are mocked so
this needs no DEEPSEEK_API_KEY and no network.

Covers:
- a query, then a near-duplicate rewording of it -> second call is a cache
  hit (ctx.trace has no 'hybrid_retrieve'/'generate' entries).
- a genuinely different query stays a cache miss (full pipeline runs).
- enabled=False -> stage is a no-op (matches the disabled-by-default test
  pattern other stages use, e.g. test_post_hoc_verify.py's
  test_disabled_stage_does_not_run).
- the cached entry's answer shape matches a real (non-cached) ask() answer.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from mevzuat_rag.chunking.chunker import StructureAwareChunker
from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.ingestion.local_corpus import load_fixtures
from mevzuat_rag.pipeline.stages.semantic_cache import SemanticCacheCheckStage, SemanticCacheStoreStage


def _fake_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


def _make_fake_client() -> MagicMock:
    """One fake client whose .create() branches on the prompt content — same
    pattern as test_smoke_pipeline.py's _make_fake_client, trimmed to the
    stages this test's config actually leaves enabled (router, generate,
    post_hoc_verify)."""
    client = MagicMock()

    def _create(*_args, **kwargs):
        text = " ".join(m.get("content", "") for m in kwargs.get("messages", []))
        if '"decision"' in text:
            return _fake_response('{"decision": "RETRIEVE", "confidence": 0.9, "reason": "mevzuat sorusu"}')
        if '"is_valid"' in text:
            return _fake_response('{"is_valid": true, "reason": "mock: bağlamla tutarlı"}')
        return _fake_response("Mock grounded cevap [1].")

    client.chat.completions.create.side_effect = _create
    return client


def _make_config(tmp: str, collection: str, *, semantic_cache_enabled: bool) -> RAGConfig:
    config = RAGConfig.from_env()
    config.qdrant_local_path = tmp
    config.qdrant_collection = collection
    config.semantic_cache.enabled = semantic_cache_enabled
    # Trim the other optional stages down to keep this test fast/focused —
    # none of them are what's under test here, and rerank in particular
    # would load a second (cross-encoder) model. router + post_hoc_verify
    # stay on: router proves it gets skipped on a cache hit, post_hoc_verify
    # proves the cached answer shape matches a real fully-verified answer.
    config.multi_query.enabled = False
    config.hyde.enabled = False
    config.rerank.enabled = False
    config.parent_doc.enabled = False
    config.crag.enabled = False
    config.compression.enabled = False
    config.citation_expansion.enabled = False
    return config


def _index_fixtures(engine: RAGEngine) -> None:
    chunker = StructureAwareChunker(max_tokens=engine.config.chunk_max_tokens)
    for raw_doc in load_fixtures()[:2]:
        doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
        engine.index_chunks(chunker.chunk(doc))


_PATCHES = (
    patch("mevzuat_rag.pipeline.stages.post_hoc_verify.get_client"),
    patch("mevzuat_rag.pipeline.stages.router.get_client"),
    patch("mevzuat_rag.generation.get_client"),
)


def _patch_all(fn):
    for p in reversed(_PATCHES):
        fn = p(fn)
    return fn


class SemanticCacheHitMissTest(unittest.TestCase):
    @_patch_all
    def test_near_duplicate_rewording_is_a_cache_hit_and_skips_retrieval_and_generation(
        self, mock_generation, mock_router, mock_post_hoc_verify
    ):
        fake_client = _make_fake_client()
        for mock_get_client in (mock_generation, mock_router, mock_post_hoc_verify):
            mock_get_client.return_value = fake_client

        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp, "semantic_cache_hit_test", semantic_cache_enabled=True)
            engine = RAGEngine(config)
            _index_fixtures(engine)

            first_query = "Dilekçe hakkının amacı nedir?"
            reworded_query = "Dilekçe hakkının amacı ne için vardır?"

            ctx1 = engine._run(first_query, top_k=5, want_answer=True)
            self.assertFalse(ctx1.answer_from_cache)
            stages1 = {t.stage for t in ctx1.trace}
            self.assertIn("hybrid_retrieve", stages1)
            self.assertIn("generate", stages1)
            self.assertIn("semantic_cache_store", stages1)
            first_answer = ctx1.answer
            self.assertTrue(first_answer["answer"])

            ctx2 = engine._run(reworded_query, top_k=5, want_answer=True)
            self.assertTrue(ctx2.answer_from_cache, "rewording of the same question should hit the semantic cache")
            self.assertTrue(ctx2.stopped)
            self.assertEqual(ctx2.stopped_reason, "semantic_cache:hit")
            stages2 = {t.stage for t in ctx2.trace}
            self.assertNotIn("hybrid_retrieve", stages2, "cache hit must skip retrieval")
            self.assertNotIn("generate", stages2, "cache hit must skip LLM generation")
            self.assertNotIn("router", stages2, "cache hit must skip every downstream stage, including router")
            self.assertNotIn("post_hoc_verify", stages2)
            self.assertNotIn("semantic_cache_store", stages2, "a cache-hit answer must not be re-stored")
            self.assertEqual(stages2, {"semantic_cache_check"})

            # the answer served for the reworded query is exactly the cached
            # (first call's) answer.
            self.assertEqual(ctx2.answer["answer"], first_answer["answer"])
            self.assertEqual(ctx2.answer["citations"], first_answer["citations"])

    @_patch_all
    def test_genuinely_different_query_is_a_cache_miss(self, mock_generation, mock_router, mock_post_hoc_verify):
        fake_client = _make_fake_client()
        for mock_get_client in (mock_generation, mock_router, mock_post_hoc_verify):
            mock_get_client.return_value = fake_client

        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp, "semantic_cache_miss_test", semantic_cache_enabled=True)
            engine = RAGEngine(config)
            _index_fixtures(engine)

            ctx1 = engine._run("Dilekçe hakkının amacı nedir?", top_k=5, want_answer=True)
            self.assertFalse(ctx1.answer_from_cache)

            # unrelated question (resmi yazışma kağıt boyutu vs. dilekçe
            # hakkının amacı) — calibrated in NOTES.md-style scratch check
            # (see config.py's SemanticCacheConfig.similarity_threshold
            # comment) to score well under the 0.90 threshold.
            ctx2 = engine._run("Resmi yazışmalarda kağıt boyutu nedir?", top_k=5, want_answer=True)
            self.assertFalse(ctx2.answer_from_cache, "an unrelated question must not hit the cache")
            stages2 = {t.stage for t in ctx2.trace}
            self.assertIn("hybrid_retrieve", stages2)
            self.assertIn("generate", stages2)
            self.assertIn("semantic_cache_store", stages2)


class SemanticCacheDisabledTest(unittest.TestCase):
    def test_check_stage_disabled_by_default_is_a_no_op(self):
        stage = SemanticCacheCheckStage(enabled=False)
        assert stage.enabled is False
        # Pipeline runner devre dışı stage'i hiç çağırmaz (bkz. runner.py) —
        # burada doğrudan .run() çağırmıyoruz, yalnızca enabled=False'ın
        # kaydedildiğini doğruluyoruz (bkz. test_post_hoc_verify.py'nin aynı
        # desendeki test_disabled_stage_does_not_run'ı).

    def test_store_stage_disabled_by_default_is_a_no_op(self):
        stage = SemanticCacheStoreStage(enabled=False)
        assert stage.enabled is False

    def test_default_config_semantic_cache_is_disabled(self):
        config = RAGConfig.from_env()
        assert config.semantic_cache.enabled is False, (
            "yeni teknikler bu depoda önce enabled: false ile eklenip test edildikten sonra "
            "açılır (bkz. README) — semantic_cache henüz canlı bir DEEPSEEK_API_KEY ile "
            "uçtan uca doğrulanmadı"
        )

    @_patch_all
    def test_disabled_semantic_cache_never_short_circuits_the_pipeline(
        self, mock_generation, mock_router, mock_post_hoc_verify
    ):
        """enabled=False iken pipeline tamamen eskisi gibi çalışır — iki kez
        aynı soru sorulsa bile her seferinde tam pipeline (retrieval +
        generation) çalışmalı, önbellek hiç devreye girmemeli."""
        fake_client = _make_fake_client()
        for mock_get_client in (mock_generation, mock_router, mock_post_hoc_verify):
            mock_get_client.return_value = fake_client

        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp, "semantic_cache_disabled_test", semantic_cache_enabled=False)
            engine = RAGEngine(config)
            _index_fixtures(engine)

            query = "Dilekçe hakkının amacı nedir?"
            for _ in range(2):
                ctx = engine._run(query, top_k=5, want_answer=True)
                self.assertFalse(ctx.answer_from_cache)
                stages = {t.stage for t in ctx.trace}
                self.assertIn("hybrid_retrieve", stages)
                self.assertIn("generate", stages)
                self.assertNotIn("semantic_cache_check", stages)
                self.assertNotIn("semantic_cache_store", stages)


class SemanticCacheAnswerShapeTest(unittest.TestCase):
    @_patch_all
    def test_cached_answer_shape_matches_real_ask_answer_shape(
        self, mock_generation, mock_router, mock_post_hoc_verify
    ):
        fake_client = _make_fake_client()
        for mock_get_client in (mock_generation, mock_router, mock_post_hoc_verify):
            mock_get_client.return_value = fake_client

        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp, "semantic_cache_shape_test", semantic_cache_enabled=True)
            engine = RAGEngine(config)
            _index_fixtures(engine)

            real_answer = engine.ask("Dilekçe hakkının amacı nedir?", top_k=5)
            cached_answer = engine.ask("Dilekçe hakkının amacı ne için vardır?", top_k=5)

            for key in ("answer", "citations", "sources"):
                self.assertIn(key, real_answer)
                self.assertIn(key, cached_answer, f"cached answer is missing '{key}' present in a real ask() answer")

            self.assertIsInstance(cached_answer["answer"], str)
            self.assertIsInstance(cached_answer["citations"], list)
            self.assertIsInstance(cached_answer["sources"], list)
            for source in cached_answer["sources"]:
                self.assertIn("citation", source)
                self.assertIn("score", source)
                self.assertIn("text", source)

            # round-trips through Qdrant's JSON payload cleanly (no tuples/
            # dataclasses left over) — this is what json.dumps would choke on
            # if the stored shape ever drifted from a plain dict.
            json.dumps(cached_answer)

            self.assertEqual(cached_answer["answer"], real_answer["answer"])
            self.assertEqual(cached_answer["citations"], real_answer["citations"])


if __name__ == "__main__":
    unittest.main()
