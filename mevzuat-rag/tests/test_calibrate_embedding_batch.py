"""Unit tests for ``scripts/calibrate_embedding_batch.py``.

Runs fully offline: no SentenceTransformer, no GPU, no model download.
Every path that would call the real embedding model is mocked. This only
covers the script's own logic (corpus building, batch-size parsing, OOM
detection/handling, best-result selection) — the real end-to-end run is a
one-off manual check (``python scripts/calibrate_embedding_batch.py --quick``),
not part of this automated suite.
"""
from __future__ import annotations

import itertools
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from mevzuat_rag.config import EmbeddingConfig  # noqa: E402
from mevzuat_rag.errors import EmbeddingOOMError  # noqa: E402
from scripts import calibrate_embedding_batch as cal  # noqa: E402

SAMPLE_DATA_DIR = Path(__file__).resolve().parents[1] / "sample_data" / "legislation"


def _embedding_config(**overrides) -> EmbeddingConfig:
    base = EmbeddingConfig()
    return replace(base, **overrides)


class ExtractMaddeTextsTests(unittest.TestCase):
    def test_extracts_real_madde_texts_from_sample_data(self):
        texts = cal.extract_madde_texts(SAMPLE_DATA_DIR)

        self.assertGreaterEqual(len(texts), 2)
        for text in texts:
            self.assertTrue(text.startswith("MADDE"))
            # Lorem ipsum değil, gerçek Türkçe mevzuat metni bekleniyor.
            self.assertNotIn("lorem", text.lower())

    def test_raises_when_no_madde_text_found(self):
        with self.assertRaises(RuntimeError):
            cal.extract_madde_texts(Path(__file__).resolve().parent)


class BuildSyntheticCorpusTests(unittest.TestCase):
    def test_cycles_base_texts_to_requested_count(self):
        base = ["MADDE 1- a", "MADDE 2- b"]
        corpus = cal.build_synthetic_corpus(base, 5)

        self.assertEqual(len(corpus), 5)
        self.assertEqual(corpus, ["MADDE 1- a", "MADDE 2- b", "MADDE 1- a", "MADDE 2- b", "MADDE 1- a"])

    def test_rejects_nonpositive_count(self):
        with self.assertRaises(ValueError):
            cal.build_synthetic_corpus(["x"], 0)
        with self.assertRaises(ValueError):
            cal.build_synthetic_corpus(["x"], -3)


class ParseBatchSizesTests(unittest.TestCase):
    def test_parses_valid_increasing_list(self):
        self.assertEqual(cal.parse_batch_sizes("8,16,32,64"), [8, 16, 32, 64])

    def test_strips_whitespace(self):
        self.assertEqual(cal.parse_batch_sizes(" 8, 16 , 32"), [8, 16, 32])

    def test_rejects_empty_string(self):
        with self.assertRaises(ValueError):
            cal.parse_batch_sizes("")

    def test_rejects_non_increasing_order(self):
        with self.assertRaises(ValueError):
            cal.parse_batch_sizes("32,16,8")

    def test_rejects_nonpositive_values(self):
        with self.assertRaises(ValueError):
            cal.parse_batch_sizes("8,0,32")
        with self.assertRaises(ValueError):
            cal.parse_batch_sizes("8,-16,32")


class IsOomErrorTests(unittest.TestCase):
    def test_detects_embedding_oom_error(self):
        self.assertTrue(cal.is_oom_error(EmbeddingOOMError("OOM")))

    def test_detects_generic_runtime_error_by_message(self):
        self.assertTrue(cal.is_oom_error(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")))

    def test_detects_torch_cuda_out_of_memory_error(self):
        try:
            import torch
        except ImportError:
            self.skipTest("torch kurulu değil")

        self.assertTrue(cal.is_oom_error(torch.cuda.OutOfMemoryError("CUDA out of memory")))

    def test_unrelated_error_is_not_oom(self):
        self.assertFalse(cal.is_oom_error(ValueError("something else entirely")))
        self.assertFalse(cal.is_oom_error(RuntimeError("connection timed out")))


class CalibrateTests(unittest.TestCase):
    def setUp(self):
        self.model = object()
        self.corpus = ["metin"] * 10
        self.config = _embedding_config(batch_size=32)

    def test_stops_at_first_oom_and_keeps_previous_results(self):
        def fake_embed(model, texts, *, config):
            if config.batch_size >= 64:
                raise EmbeddingOOMError("CUDA out of memory")
            return [[0.0] for _ in texts]

        with patch.object(cal, "embed_texts_with_config", side_effect=fake_embed) as mocked, patch.object(
            cal.time, "perf_counter", side_effect=itertools.count(0.0, 0.1)
        ):
            results = cal.calibrate(self.model, self.corpus, [8, 16, 64, 128, 256], self.config)

        self.assertEqual([r["batch_size"] for r in results], [8, 16])
        # 64'te OOM'a çarpınca döngü durmalı; 128 ve 256 hiç denenmemeli.
        self.assertEqual(mocked.call_count, 3)
        called_batch_sizes = [call.kwargs["config"].batch_size for call in mocked.call_args_list]
        self.assertEqual(called_batch_sizes, [8, 16, 64])

    def test_oom_probe_disables_internal_oom_retry(self):
        """calibrate() kendi OOM tespitini yapabilmek için iç oom_retry'ı kapatmalı,
        yoksa embed_texts_with_config OOM'u sessizce yarı batch'le maskeler."""
        seen_configs = []

        def fake_embed(model, texts, *, config):
            seen_configs.append(config)
            return [[0.0] for _ in texts]

        with patch.object(cal, "embed_texts_with_config", side_effect=fake_embed), patch.object(
            cal.time, "perf_counter", side_effect=itertools.count(0.0, 0.1)
        ):
            cal.calibrate(self.model, self.corpus, [8], _embedding_config(batch_size=32, oom_retry=True, max_retries=5))

        self.assertEqual(len(seen_configs), 1)
        self.assertFalse(seen_configs[0].oom_retry)
        self.assertEqual(seen_configs[0].max_retries, 0)
        self.assertEqual(seen_configs[0].batch_size, 8)

    def test_unexpected_non_oom_error_is_skipped_but_loop_continues(self):
        def fake_embed(model, texts, *, config):
            if config.batch_size == 16:
                raise ValueError("beklenmedik hata")
            return [[0.0] for _ in texts]

        with patch.object(cal, "embed_texts_with_config", side_effect=fake_embed), patch.object(
            cal.time, "perf_counter", side_effect=itertools.count(0.0, 0.1)
        ):
            results = cal.calibrate(self.model, self.corpus, [8, 16, 32], self.config)

        self.assertEqual([r["batch_size"] for r in results], [8, 32])

    def test_never_raises_even_when_every_batch_size_fails(self):
        def fake_embed(model, texts, *, config):
            raise RuntimeError("out of memory")

        with patch.object(cal, "embed_texts_with_config", side_effect=fake_embed), patch.object(
            cal.time, "perf_counter", side_effect=itertools.count(0.0, 0.1)
        ):
            results = cal.calibrate(self.model, self.corpus, [8, 16], self.config)

        self.assertEqual(results, [])


class BestResultTests(unittest.TestCase):
    def test_selects_highest_throughput(self):
        results = [
            {"batch_size": 8, "throughput_chunks_per_s": 100.0},
            {"batch_size": 64, "throughput_chunks_per_s": 400.0},
            {"batch_size": 32, "throughput_chunks_per_s": 250.0},
        ]
        self.assertEqual(cal.best_result(results)["batch_size"], 64)

    def test_empty_results_returns_none(self):
        self.assertIsNone(cal.best_result([]))


if __name__ == "__main__":
    unittest.main()
