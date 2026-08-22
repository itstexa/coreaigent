"""[5] Güvenlik — PII redaksiyonu sonrası veri saklama/silme politikası testleri.

Uygulaması: docs/IMPROVEMENT_IDEAS.md, "3. Güvenlik, Gizlilik ve Uyumluluk"
bölümü, madde 5. Gerçek (tempfile ile izole edilmiş embedded) bir Qdrant'a
chunk'lar indekslenir, bazılarının ``indexed_at`` payload alanı doğrudan
``client.set_payload`` ile eski bir tarihe çekilir, sonra
``list_retention_candidates``/``delete_older_than``'in yalnızca eski
chunk'ları bulup sildiğini, yeni/güncel chunk'lara DOKUNMADIĞINI kanıtlar.
"""
from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from mevzuat_rag.models import ChunkMetadata, LegislationChunk
from mevzuat_rag.retention import delete_older_than, list_retention_candidates
from mevzuat_rag.store import QdrantStore

VECTOR_SIZE = 1024


def _chunk_id(name: str) -> str:
    """Qdrant point id'leri UUID veya unsigned int olmak zorunda (bkz.
    chunker.py'nin ``uuid.uuid5`` kullanımı) — test okunabilirliği için
    kısa isimlerden deterministik UUID üretir."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def _make_chunk(name: str, kanun_no: str, madde_no: int) -> LegislationChunk:
    metadata = ChunkMetadata(
        kanun_no=kanun_no,
        kanun_adi="Test Kanunu",
        madde_no=madde_no,
        fikra_no=None,
        bent=None,
        kaynak_url="https://example.test",
        source_hash=f"hash-{name}",
    )
    return LegislationChunk(id=_chunk_id(name), text=f"Madde {madde_no} metni.", metadata=metadata, citation=f"{kanun_no} sayılı, Madde {madde_no}")


def _dummy_vector() -> list[float]:
    return [0.001] * VECTOR_SIZE


def _set_indexed_at(store: QdrantStore, name: str, when: datetime) -> None:
    """Testte 'geçmişte indekslenmiş' durumunu simüle eder — gerçek bir
    upsert_chunks çağrısından sonra store'a doğrudan erişip tek bir point'in
    payload'ındaki indexed_at'i override eder."""
    store.client.set_payload(
        collection_name=store.collection,
        payload={"indexed_at": when.isoformat()},
        points=[_chunk_id(name)],
    )


class RetentionTests(unittest.TestCase):
    def test_list_retention_candidates_finds_only_old_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = QdrantStore(collection="retention_list_test", local_path=tmp)

            old_chunk = _make_chunk("old-1", "1111", 1)
            fresh_chunk = _make_chunk("fresh-1", "1111", 2)
            store.upsert_chunks([old_chunk, fresh_chunk], [_dummy_vector(), _dummy_vector()])

            _set_indexed_at(store, "old-1", datetime.now(timezone.utc) - timedelta(days=400))

            candidates = list_retention_candidates(store, days=365)
            candidate_ids = {c["id"] for c in candidates}

            self.assertIn(_chunk_id("old-1"), candidate_ids)
            self.assertNotIn(_chunk_id("fresh-1"), candidate_ids)

            old = next(c for c in candidates if c["id"] == _chunk_id("old-1"))
            self.assertEqual(old["kanun_no"], "1111")
            self.assertEqual(old["madde_no"], 1)
            self.assertIsNotNone(old["indexed_at"])

    def test_list_retention_candidates_is_dry_run_and_deletes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = QdrantStore(collection="retention_dryrun_test", local_path=tmp)
            chunk = _make_chunk("only-1", "1111", 1)
            store.upsert_chunks([chunk], [_dummy_vector()])
            _set_indexed_at(store, "only-1", datetime.now(timezone.utc) - timedelta(days=400))

            list_retention_candidates(store, days=365)

            remaining = store.client.count(collection_name="retention_dryrun_test").count
            self.assertEqual(remaining, 1)

    def test_delete_older_than_deletes_old_and_keeps_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = QdrantStore(collection="retention_delete_test", local_path=tmp)

            old_chunk = _make_chunk("old-2", "2222", 1)
            fresh_chunk = _make_chunk("fresh-2", "2222", 2)
            store.upsert_chunks([old_chunk, fresh_chunk], [_dummy_vector(), _dummy_vector()])
            _set_indexed_at(store, "old-2", datetime.now(timezone.utc) - timedelta(days=400))

            deleted_count = delete_older_than(store, days=365)
            self.assertEqual(deleted_count, 1)

            remaining_ids = {str(p.id) for p in store.client.scroll(collection_name="retention_delete_test", limit=100)[0]}
            self.assertNotIn(_chunk_id("old-2"), remaining_ids)
            self.assertIn(_chunk_id("fresh-2"), remaining_ids)

    def test_delete_older_than_returns_zero_when_nothing_is_old(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = QdrantStore(collection="retention_none_test", local_path=tmp)
            chunk = _make_chunk("fresh-3", "3333", 1)
            store.upsert_chunks([chunk], [_dummy_vector()])

            deleted_count = delete_older_than(store, days=365)
            self.assertEqual(deleted_count, 0)

            remaining = store.client.count(collection_name="retention_none_test").count
            self.assertEqual(remaining, 1)

    def test_missing_indexed_at_is_treated_as_retention_candidate(self) -> None:
        """Legacy point'ler (upsert_chunks bu alanı yazmadan önce indekslenmiş)
        indexed_at'i hiç taşımıyor olabilir — KVKK açısından en riskli durum,
        bu yüzden 'ne zaman indekslendiği bilinmiyor' -> silme adayı sayılmalı."""
        with tempfile.TemporaryDirectory() as tmp:
            store = QdrantStore(collection="retention_legacy_test", local_path=tmp)
            chunk = _make_chunk("legacy-1", "4444", 1)
            store.upsert_chunks([chunk], [_dummy_vector()])

            # indexed_at alanını tamamen kaldırarak legacy (upsert_chunks'tan
            # önceki) bir point'i simüle et.
            store.client.delete_payload(
                collection_name="retention_legacy_test",
                keys=["indexed_at"],
                points=[_chunk_id("legacy-1")],
            )

            candidates = list_retention_candidates(store, days=365)
            self.assertEqual({c["id"] for c in candidates}, {_chunk_id("legacy-1")})


class ApplyRetentionPolicyCliTests(unittest.TestCase):
    def test_cli_dry_run_by_default_deletes_nothing(self) -> None:
        import subprocess
        import sys
        from pathlib import Path

        mevzuat_rag_root = Path(__file__).resolve().parents[1]
        script = mevzuat_rag_root / "scripts" / "apply_retention_policy.py"

        with tempfile.TemporaryDirectory() as tmp:
            store = QdrantStore(collection="retention_cli_test", local_path=tmp)
            chunk = _make_chunk("cli-1", "5555", 1)
            store.upsert_chunks([chunk], [_dummy_vector()])
            _set_indexed_at(store, "cli-1", datetime.now(timezone.utc) - timedelta(days=400))
            store.client.close()

            env = {
                "QDRANT_LOCAL_PATH": tmp,
                "QDRANT_COLLECTION_MEVZUAT": "retention_cli_test",
                "PATH": "/usr/bin:/bin",
            }
            result = subprocess.run(
                [sys.executable, str(script), "--days", "365"],
                cwd=str(mevzuat_rag_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Kuru çalışma", result.stdout)

            verify_store = QdrantStore(collection="retention_cli_test", local_path=tmp)
            remaining = verify_store.client.count(collection_name="retention_cli_test").count
            self.assertEqual(remaining, 1)

    def test_cli_confirm_actually_deletes(self) -> None:
        import subprocess
        import sys
        from pathlib import Path

        mevzuat_rag_root = Path(__file__).resolve().parents[1]
        script = mevzuat_rag_root / "scripts" / "apply_retention_policy.py"

        with tempfile.TemporaryDirectory() as tmp:
            store = QdrantStore(collection="retention_cli_confirm_test", local_path=tmp)
            old_chunk = _make_chunk("cli-old", "6666", 1)
            fresh_chunk = _make_chunk("cli-fresh", "6666", 2)
            store.upsert_chunks([old_chunk, fresh_chunk], [_dummy_vector(), _dummy_vector()])
            _set_indexed_at(store, "cli-old", datetime.now(timezone.utc) - timedelta(days=400))
            store.client.close()

            env = {
                "QDRANT_LOCAL_PATH": tmp,
                "QDRANT_COLLECTION_MEVZUAT": "retention_cli_confirm_test",
                "PATH": "/usr/bin:/bin",
            }
            result = subprocess.run(
                [sys.executable, str(script), "--days", "365", "--confirm"],
                cwd=str(mevzuat_rag_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("1 chunk silindi", result.stdout)

            verify_store = QdrantStore(collection="retention_cli_confirm_test", local_path=tmp)
            remaining_ids = {str(p.id) for p in verify_store.client.scroll(collection_name="retention_cli_confirm_test", limit=100)[0]}
            self.assertNotIn(_chunk_id("cli-old"), remaining_ids)
            self.assertIn(_chunk_id("cli-fresh"), remaining_ids)


if __name__ == "__main__":
    unittest.main()
