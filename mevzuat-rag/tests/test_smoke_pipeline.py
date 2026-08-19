"""GPU-free smoke test for the full [0]-[7] pipeline (spec: "3 örnek doküman
ingest et, 3 sorgu at, her stage'in trace'i dolu mu kontrol et... GPU'suz da
geçmeli, mock LLM ile"). Runs on CPU with the real embedding model + real
embedded Qdrant + real chunking/retrieval — only the DeepSeek/LLM calls
(router, multi-query, HyDE, CRAG, generate) are mocked, so this needs no
DEEPSEEK_API_KEY and no network. This is the first automated check that the
whole default.yaml pipeline (all stages enabled) actually wires together
end-to-end on a fresh machine — see scripts/verify_env.py for the
non-automated, human-run equivalent.
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

EXPECTED_STAGES = {
    "router", "multi_query", "hyde", "hybrid_retrieve", "embed_query",
    "rerank", "parent_doc", "crag", "compression", "generate",
}


def _fake_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    return response


def _make_fake_client() -> MagicMock:
    """One fake client whose .create() branches on the prompt content to
    return the shape each caller's parser expects — router/CRAG/multi-query/
    HyDE/generate all go through this one mocked client."""
    client = MagicMock()

    def _create(*_args, **kwargs):
        text = " ".join(m.get("content", "") for m in kwargs.get("messages", []))
        if '"decision"' in text:
            return _fake_response('{"decision": "RETRIEVE", "confidence": 0.9, "reason": "mevzuat sorusu"}')
        if '"verdict"' in text:
            return _fake_response('{"verdict": "SUFFICIENT", "missing_aspect": "", "reason": "yeterli"}')
        if "JSON dizisi" in text:
            return _fake_response(json.dumps(["mock sorgu bir", "mock sorgu iki"]))
        if "hipotetik" in text.lower():
            return _fake_response("Mock hipotetik cevap metni.")
        return _fake_response("Mock grounded cevap [1].")

    client.chat.completions.create.side_effect = _create
    return client


class SmokePipelineTest(unittest.TestCase):
    # Each stage module did `from mevzuat_rag.llm_client import get_client`,
    # binding its own local name — patching mevzuat_rag.llm_client.get_client
    # alone would not reach any of them, so every call site is patched here.
    @patch("mevzuat_rag.pipeline.stages.crag.get_client")
    @patch("mevzuat_rag.pipeline.stages.hyde.get_client")
    @patch("mevzuat_rag.pipeline.stages.multi_query.get_client")
    @patch("mevzuat_rag.pipeline.stages.router.get_client")
    @patch("mevzuat_rag.generation.get_client")
    def test_full_pipeline_all_stages_traced(self, mock_generation, mock_router, mock_multi_query, mock_hyde, mock_crag):
        fake_client = _make_fake_client()
        for mock_get_client in (mock_generation, mock_router, mock_multi_query, mock_hyde, mock_crag):
            mock_get_client.return_value = fake_client

        with tempfile.TemporaryDirectory() as tmp:
            config = RAGConfig.from_env()
            config.qdrant_local_path = tmp
            config.qdrant_collection = "smoke_test_all_stages"
            engine = RAGEngine(config)

            chunker = StructureAwareChunker(max_tokens=config.chunk_max_tokens)
            for raw_doc in load_fixtures()[:3]:
                doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
                engine.index_chunks(chunker.chunk(doc))

            for query in [
                "Dilekçe hakkının amacı nedir?",
                "Resmi yazışmalarda kağıt boyutu nedir?",
                "Hangi dilekçeler incelenemez?",
            ]:
                ctx = engine._run(query, top_k=5, want_answer=True)
                traced_stages = {t.stage for t in ctx.trace}
                self.assertEqual(traced_stages, EXPECTED_STAGES, f"'{query}': trace {traced_stages} != {EXPECTED_STAGES}")
                self.assertTrue(all(t.duration_ms >= 0 for t in ctx.trace))
                self.assertIsNotNone(ctx.answer)
                self.assertIn("answer", ctx.answer)
                self.assertTrue(ctx.answer["answer"])


if __name__ == "__main__":
    unittest.main()
