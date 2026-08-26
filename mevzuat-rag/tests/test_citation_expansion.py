"""[9] Atıf Genişletme entegrasyon testi — gerçek corpus, gerçek embedding,
gerçek Qdrant (LLM yok, retrieve() yeterli).

Gerçek durum: "Hangi dilekçeler incelenemez?" sorusu semantik olarak Madde 6'yı
buluyor (skor 0.997) ama Madde 4'ü BULMUYOR (doğrulandı — bkz. bu testin
kendisi, min_score=0.05 sonrası yalnızca Madde 6/8/9 dönüyor). Oysa Madde
6.c metni açıkça "4. maddede gösterilen şartlar" diyor. Bu, [9]'un çözdüğü
gerçek boşluk.
"""
from __future__ import annotations

import tempfile

from mevzuat_rag.chunking.chunker import StructureAwareChunker
from mevzuat_rag.chunking.legal_structure_parser import parse_legislation_text
from mevzuat_rag.config import RAGConfig
from mevzuat_rag.engine import RAGEngine
from mevzuat_rag.ingestion.local_corpus import load_fixtures


def _make_engine(tmp_qdrant: str, collection: str, citation_expansion_enabled: bool) -> RAGEngine:
    config = RAGConfig.from_env()
    config.qdrant_local_path = tmp_qdrant
    config.qdrant_collection = collection
    config.citation_expansion.enabled = citation_expansion_enabled
    engine = RAGEngine(config)

    chunker = StructureAwareChunker(max_tokens=config.chunk_max_tokens)
    for raw_doc in load_fixtures():
        doc = parse_legislation_text(raw_doc.raw_text, raw_doc.kanun_no, raw_doc.kanun_adi, raw_doc.url)
        engine.index_chunks(chunker.chunk(doc))
    return engine


def test_madde4_missing_without_citation_expansion():
    with tempfile.TemporaryDirectory() as tmp:
        engine = _make_engine(tmp, "citation_expansion_off_test", citation_expansion_enabled=False)
        hits = engine.retrieve("Hangi dilekçeler incelenemez?", top_k=5)
        madde_nos = {h.chunk.metadata.madde_no for h in hits}
        assert 4 not in madde_nos, "bu test [9] olmadan Madde 4'ün BULUNMADIĞINI kanıtlamalı"
        assert 6 in madde_nos


def test_madde4_pulled_in_by_citation_expansion():
    with tempfile.TemporaryDirectory() as tmp:
        engine = _make_engine(tmp, "citation_expansion_on_test", citation_expansion_enabled=True)
        hits = engine.retrieve("Hangi dilekçeler incelenemez?", top_k=10)
        madde_nos = {h.chunk.metadata.madde_no for h in hits}
        assert 6 in madde_nos
        assert 4 in madde_nos, "[9] Madde 6.c'nin '4. maddede' atfını takip edip Madde 4'ü eklemeliydi"

        expanded = next(h for h in hits if h.chunk.metadata.madde_no == 4)
        assert "atıf üzerinden genişletildi" in expanded.chunk.citation


def test_citation_expansion_does_not_duplicate_already_present_madde():
    """Zaten getirilmiş bir maddeye tekrar atıf varsa ikinci bir kopya eklenmemeli."""
    with tempfile.TemporaryDirectory() as tmp:
        engine = _make_engine(tmp, "citation_expansion_dedup_test", citation_expansion_enabled=True)
        hits = engine.retrieve("Hangi dilekçeler incelenemez?", top_k=10)
        # kanun_no'yu da filtrelemek gerekiyor: corpus artık 4 belge içeriyor
        # (offline_docs ile KVKK/Bilgi Edinme/Yönetmelik eklendi), bu yüzden
        # başka bir kanunun Madde 6'sı da top_k=10 içine girebilir — asıl test
        # ettiğimiz şey 3071'in kendi Madde 6'sının tekilleştirilmesi.
        madde6_hits = [h for h in hits if h.chunk.metadata.kanun_no == "3071" and h.chunk.metadata.madde_no == 6]
        assert len(madde6_hits) == 1
