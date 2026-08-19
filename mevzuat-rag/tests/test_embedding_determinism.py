"""Bitwise determinism tests for the embedding layer.

These tests intentionally use the real local BGE-M3 model on CPU. If
repeated calls, batch composition, or input order change any vector, the
tests fail at bit level. That is deliberate: unstable vectors break
retrieval consistency and are not a harmless implementation detail.
"""
from __future__ import annotations

import unittest

import numpy as np

from mevzuat_rag.embedding import embed_query, embed_texts, get_embedder

MODEL_NAME = "BAAI/bge-m3"


class EmbeddingDeterminismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = get_embedder(MODEL_NAME, "cpu")

    def _assert_same_vector(self, left, right, msg: str = "") -> None:
        np.testing.assert_array_equal(
            np.asarray(left, dtype=float),
            np.asarray(right, dtype=float),
            err_msg=msg,
        )

    def test_embedding_is_deterministic(self):
        text = "Dilekçe hakkının amacı nedir?"

        first = embed_texts(self.model, [text])[0]
        second = embed_texts(self.model, [text])[0]
        query_vec = embed_query(self.model, text)

        self._assert_same_vector(
            first,
            second,
            "embed_texts() repeated call changed the vector",
        )
        self._assert_same_vector(
            first,
            query_vec,
            "embed_query() does not match embed_texts()",
        )

    def test_embedding_is_batch_invariant(self):
        """If this fails, batch padding/normalization is changing vectors.

        A single text must produce the same vector whether it is embedded
        alone or as part of a larger batch. Batch-size-dependent vectors
        break reproducibility for query/document matching.
        """
        text = "3071 sayılı Dilekçe Kanunu'nun bir maddesi"

        single = embed_texts(self.model, [text])[0]
        batch4 = embed_texts(self.model, [text] * 4)[0]
        batch32 = embed_texts(self.model, [text] * 32)[0]

        self._assert_same_vector(
            single,
            batch4,
            "first-item vector changed when batch size was 4",
        )
        self._assert_same_vector(
            single,
            batch32,
            "first-item vector changed when batch size was 32",
        )

    def test_embedding_is_order_invariant(self):
        texts = [
            "Dilekçe hakkı nedir?",
            "3071 sayılı Kanun kapsamında başvuru süresi",
            "Yargı mercilerinin görevine giren konular",
        ]

        forward = embed_texts(self.model, texts)
        reverse_order = [texts[2], texts[0], texts[1]]
        reverse = embed_texts(self.model, reverse_order)

        forward_by_text = dict(zip(texts, forward))
        reverse_by_text = dict(zip(reverse_order, reverse))

        for text in texts:
            self._assert_same_vector(
                forward_by_text[text],
                reverse_by_text[text],
                f"vector changed with input order for text: {text!r}",
            )
