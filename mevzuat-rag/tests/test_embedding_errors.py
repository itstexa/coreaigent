"""Unit tests for embedding error handling.

Runs fully offline: every path that would load a SentenceTransformer is
mocked, so no model download or GPU is required.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np

import mevzuat_rag.embedding as embedding_mod
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.embedding import (
    EmbeddingComputeError,
    EmbeddingDimensionError,
    EmbeddingInputError,
    EmbeddingModelLoadError,
    embed_texts,
    get_embedder,
    validate_embeddings,
)
from mevzuat_rag.engine import RAGEngine


class EmbeddingErrorTests(unittest.TestCase):
    def setUp(self):
        embedding_mod._model_cache.clear()

    def tearDown(self):
        embedding_mod._model_cache.clear()

    @staticmethod
    def _fake_embedding_config(**overrides):
        defaults = {
            "batch_size": 32,
            "min_batch_size": 1,
            "max_retries": 2,
            "oom_retry": True,
            "strict_validation": True,
            "on_overlong": "warn_truncate",
            "max_input_chars": 20000,
            "dim": 3,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_embed_texts_rejects_empty_none_blank(self):
        model = MagicMock()
        config = self._fake_embedding_config()

        with patch("mevzuat_rag.embedding._get_default_config", return_value=config):
            with self.assertRaises(EmbeddingInputError):
                embed_texts(model, [])
            with self.assertRaises(EmbeddingInputError):
                embed_texts(model, None)
            with self.assertRaises(EmbeddingInputError):
                embed_texts(model, [None])
            with self.assertRaises(EmbeddingInputError):
                embed_texts(model, [" "])

    def test_validate_embeddings_rejects_wrong_row_count(self):
        with self.assertRaises(EmbeddingDimensionError):
            validate_embeddings(
                [[1.0, 0.0, 0.0]],
                expected_count=2,
                expected_dim=3,
                check_normalized=False,
            )

    def test_validate_embeddings_rejects_wrong_vector_dim(self):
        with self.assertRaises(EmbeddingDimensionError):
            validate_embeddings(
                [[1.0, 0.0]],
                expected_count=1,
                expected_dim=3,
                check_normalized=False,
            )

    def test_validate_embeddings_rejects_nan(self):
        with self.assertRaises(EmbeddingComputeError):
            validate_embeddings(
                [[float("nan"), 0.0, 0.0]],
                expected_count=1,
                expected_dim=3,
                check_normalized=False,
            )

    def test_oom_retry_reduces_batch_size(self):
        config = self._fake_embedding_config(
            batch_size=4,
            min_batch_size=1,
            max_retries=2,
            oom_retry=True,
            strict_validation=True,
        )
        model = MagicMock()
        model.encode.side_effect = [
            RuntimeError("CUDA out of memory"),
            np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=float),
        ]

        with patch("mevzuat_rag.embedding._get_default_config", return_value=config):
            with self.assertLogs("mevzuat_rag.embedding", level="WARNING") as cm:
                vectors = embed_texts(model, ["a", "b"])

        self.assertEqual(len(vectors), 2)
        self.assertEqual(model.encode.call_count, 2)
        self.assertEqual(model.encode.call_args_list[0].kwargs["batch_size"], 4)
        self.assertEqual(model.encode.call_args_list[1].kwargs["batch_size"], 2)
        self.assertTrue(any("OOM" in message for message in cm.output))

    def test_model_load_error_wraps_and_includes_context(self):
        with patch.dict(os.environ, {"HF_HOME": "/tmp/hf"}):
            with patch(
                "mevzuat_rag.embedding.SentenceTransformer",
                side_effect=RuntimeError("download failed"),
            ):
                with self.assertRaises(EmbeddingModelLoadError) as ctx:
                    get_embedder("bge-m3", "cpu")

        message = str(ctx.exception)
        self.assertIn("bge-m3", message)
        self.assertIn("/tmp/hf", message)

    def test_ingest_batch_failure_isolates_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = RAGConfig.from_env()
            config.qdrant_local_path = tmp
            config.qdrant_collection = "test_embedding_errors_ingest"
            config.embedding.dim = 3

            mock_model = MagicMock()
            mock_model.get_sentence_embedding_dimension.return_value = 3

            engine = RAGEngine(config)
            # Bypass the lazy ``model`` property's real get_embedder() call —
            # index_chunks() accesses ``self.model`` after construction, so a
            # patch scoped only around ``RAGEngine(config)`` would already
            # have exited by then and hit the real SentenceTransformer.
            engine._model = mock_model

            engine._store = MagicMock()
            engine.store.existing_source_hashes.return_value = {}
            engine.bm25_index = MagicMock()

            chunks = [
                SimpleNamespace(
                    id=f"chunk_{i}",
                    text=f"text {i}",
                    metadata=SimpleNamespace(source_hash=f"hash_{i}"),
                )
                for i in range(3)
            ]
            chunks[2].text = "bad text"

            def fake_embed(model, texts, *, config):
                if any("bad" in text for text in texts):
                    raise RuntimeError("embed failed")
                return [[1.0, 0.0, 0.0] for _ in texts]

            with patch(
                "mevzuat_rag.engine.embed_texts_with_config",
                side_effect=fake_embed,
            ):
                result = engine.index_chunks(chunks)

        self.assertEqual(result["embedded"], 2)
        self.assertEqual(result["skipped_unchanged"], 0)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["failed"][0]["chunk_id"], "chunk_2")


if __name__ == "__main__":
    unittest.main()
