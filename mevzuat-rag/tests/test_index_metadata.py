"""Regression tests for QdrantStore index metadata checks."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mevzuat_rag.store import IndexMetadataMismatch, QdrantStore


class IndexMetadataTests(unittest.TestCase):
    """Tests for embedding model and text normalization version compatibility."""

    @staticmethod
    def _open(
        collection: str,
        tmp_path: str,
        *,
        embedding_model: str = "test-model",
        embedding_dim: int = 16,
        text_norm_version: str | None = None,
    ) -> QdrantStore:
        return QdrantStore(
            collection=collection,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            local_path=tmp_path,
            text_norm_version=text_norm_version,
        )

    def test_text_norm_version_mismatch_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            collection = "test_tnv_mismatch"
            store = self._open(collection, tmp, text_norm_version="1.0.0")
            store.client.close()

            with self.assertRaises(IndexMetadataMismatch):
                self._open(collection, tmp, text_norm_version="2.0.0")

    def test_embedding_model_mismatch_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            collection = "test_model_mismatch"
            store = self._open(
                collection,
                tmp,
                embedding_model="model-a",
                text_norm_version="1.0.0",
            )
            store.client.close()

            with self.assertRaises(IndexMetadataMismatch):
                self._open(
                    collection,
                    tmp,
                    embedding_model="model-b",
                    text_norm_version="1.0.0",
                )

    def test_text_norm_version_none_skips_version_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            collection = "test_tnv_none"
            store = self._open(collection, tmp, text_norm_version="1.0.0")
            store.client.close()

            # None means "do not enforce version", so this must not raise.
            reopened = self._open(collection, tmp, text_norm_version=None)
            reopened.client.close()

    def test_index_meta_json_contains_text_norm_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            collection = "test_meta_json"
            store = self._open(collection, tmp, text_norm_version="1.0.0")
            store.client.close()

            meta_path = Path(tmp) / f"index_meta_{collection}.json"
            self.assertTrue(meta_path.exists())

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(meta.get("text_norm_version"), "1.0.0")


if __name__ == "__main__":
    unittest.main()
