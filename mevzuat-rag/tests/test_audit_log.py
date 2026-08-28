"""Audit log testleri — 2026-08-22 alt-ajan taramasında bulunan boşluk
(docs/IMPROVEMENT_IDEAS.md, Güvenlik #2)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from mevzuat_rag import audit_log
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.ingestion.local_corpus import load_fixtures


def test_log_query_writes_valid_jsonl_row(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    audit_log.log_query("test sorgu", citations=["1111 sayılı Test, Madde 1"], log_path=log_path)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["query"] == "test sorgu"
    assert row["citations"] == ["1111 sayılı Test, Madde 1"]
    assert row["actor"] is None
    assert "timestamp" in row


def test_log_query_is_append_only(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    audit_log.log_query("soru 1", citations=[], log_path=log_path)
    audit_log.log_query("soru 2", citations=[], log_path=log_path)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["query"] == "soru 1"
    assert json.loads(lines[1])["query"] == "soru 2"


def test_log_query_never_includes_raw_chunk_text(tmp_path: Path):
    """Audit log yalnızca citation string'lerini taşımalı, ham metin değil —
    aksi halde audit log'un kendisi ayrı bir PII sızıntı yüzeyi olur."""
    log_path = tmp_path / "audit.jsonl"
    audit_log.log_query("soru", citations=["1111 sayılı Test, Madde 1"], log_path=log_path)
    row = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert set(row.keys()) == {"timestamp", "actor", "query", "citations", "answer_verdict"}


def test_engine_retrieve_writes_audit_entry():
    with tempfile.TemporaryDirectory() as tmp:
        config = RAGConfig.from_env()
        config.qdrant_local_path = tmp
        config.qdrant_collection = "audit_log_retrieve_test"
        engine = RAGEngine(config)

        from mevzuat_rag.chunking.chunker import StructureAwareChunker
        from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text

        chunker = StructureAwareChunker(max_tokens=config.chunk_max_tokens)
        raw_doc = load_fixtures()[0]
        doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
        engine.index_chunks(chunker.chunk(doc))

        with patch("mevzuat_rag.engine.audit_log.log_query") as mock_log:
            engine.retrieve("dilekçe hakkında soru", top_k=3)
            mock_log.assert_called_once()
            _, kwargs = mock_log.call_args
            assert mock_log.call_args[0][0] == "dilekçe hakkında soru"
            assert "citations" in kwargs
            assert kwargs.get("actor") is None

        with patch("mevzuat_rag.engine.audit_log.log_query") as mock_log:
            engine.retrieve("dilekçe hakkında soru", top_k=3, actor="test:operator_1")
            _, kwargs = mock_log.call_args
            assert kwargs.get("actor") == "test:operator_1", (
                "engine.retrieve()'e geçirilen actor, audit_log.log_query()'e "
                "ulaşmıyor — erişim kontrolü denetiminde bulunan boşluk "
                "(audit_log.actor hep None) yeniden açılmış olabilir."
            )
