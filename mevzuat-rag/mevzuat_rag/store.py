"""Qdrant-backed storage for legislation chunks.

Same collection shape as ``insangram/src/rag/embed.py``: a single unnamed
dense cosine vector per point, no sparse/hybrid fusion (BM25 is a separate
in-memory index, see pipeline/bm25_index.py). Supports either a remote
Qdrant server (``QDRANT_URL``, used by ``compose.yaml``'s ``qdrant``
service) or an embedded on-disk client (``QDRANT_LOCAL_PATH``, useful for the
smoke test and local dev without Docker) — same fallback Insangram uses.

Fail-fast on embedding mismatch: a small ``index_meta_{collection}.json``
next to the local Qdrant data records which embedding model/dimension built
the index. Opening an existing collection with a different model/dim raises
immediately instead of silently returning wrong-dimension nonsense results
later. See DEPLOY.md / MIGRATION.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from mevzuat_rag.models import ChunkMetadata, LegislationChunk, RetrievalResult


class IndexMetadataMismatch(RuntimeError):
    pass


class QdrantStore:
    def __init__(
        self,
        collection: str,
        url: str | None = None,
        local_path: str | None = None,
        embedding_model: str = "BAAI/bge-m3",
        embedding_dim: int = 1024,
        meta_dir: str | None = None,
        *,
        text_norm_version: str | None = None,
    ):
        self.collection = collection
        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self.text_norm_version = text_norm_version
        self.client = QdrantClient(url=url) if url else QdrantClient(path=local_path)
        self._meta_path = Path(meta_dir or local_path or ".") / f"index_meta_{collection}.json"
        self._ensure_collection()
        self._check_index_metadata()

    def _ensure_collection(self) -> None:
        names = [c.name for c in self.client.get_collections().collections]
        if self.collection not in names:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.embedding_dim, distance=Distance.COSINE),
            )

    def _check_index_metadata(self) -> None:
        collection_info = self.client.get_collection(self.collection)
        actual_dim = collection_info.config.params.vectors.size
        if actual_dim != self.embedding_dim:
            raise IndexMetadataMismatch(
                f"Koleksiyon '{self.collection}' {actual_dim} boyutlu vektörlerle kurulmuş, "
                f"ama şu anki config {self.embedding_dim} boyutlu ({self.embedding_model}) bekliyor. "
                f"Farklı bir embedding modeliyle açılmaya çalışılıyor — bkz. MIGRATION.md."
            )

        if self._meta_path.exists():
            try:
                recorded = json.loads(self._meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                recorded = {}
            recorded_model = recorded.get("embedding_model")
            if recorded_model and recorded_model != self.embedding_model:
                raise IndexMetadataMismatch(
                    f"Koleksiyon '{self.collection}' '{recorded_model}' embedding modeliyle "
                    f"indekslenmiş, ama şu anki config '{self.embedding_model}' bekliyor. Aynı "
                    f"boyutta olsalar bile farklı modellerin vektör uzayları uyumlu değildir — "
                    f"bkz. MIGRATION.md."
                )
            recorded_version = recorded.get("text_norm_version")
            if self.text_norm_version is not None and recorded_version != self.text_norm_version:
                raise IndexMetadataMismatch(
                    f"Koleksiyon '{self.collection}' metin normalizasyon versiyonu "
                    f"'{recorded_version or 'tanımsız'}' ile indekslenmiş, ama şu anki config "
                    f"'{self.text_norm_version}' bekliyor. Normalizasyon kuralları değiştiğinde "
                    f"chunk metinleri/vektörleri uyumsuz hale gelir — bkz. MIGRATION.md."
                )
        else:
            self._write_index_metadata()

    def _write_index_metadata(self) -> None:
        try:
            self._meta_path.parent.mkdir(parents=True, exist_ok=True)
            metadata: dict[str, object] = {
                "embedding_model": self.embedding_model,
                "embedding_dim": self.embedding_dim,
                "collection": self.collection,
            }
            if self.text_norm_version is not None:
                metadata["text_norm_version"] = self.text_norm_version
            self._meta_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # best-effort — a remote Qdrant + read-only local fs shouldn't hard-fail startup

    def upsert_chunks(self, chunks: list[LegislationChunk], vectors: list[list[float]]) -> None:
        points = [
            PointStruct(
                id=chunk.id,
                vector=vector,
                payload={
                    "text": chunk.text,
                    "citation": chunk.citation,
                    "kanun_no": chunk.metadata.kanun_no,
                    "kanun_adi": chunk.metadata.kanun_adi,
                    "madde_no": chunk.metadata.madde_no,
                    "fikra_no": chunk.metadata.fikra_no,
                    "bent": chunk.metadata.bent,
                    "kaynak_url": chunk.metadata.kaynak_url,
                    "source_hash": chunk.metadata.source_hash,
                    "durum": chunk.metadata.durum,
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        if points:
            self.client.upsert(collection_name=self.collection, points=points)

    def existing_source_hashes(self, chunk_ids: list[str]) -> dict[str, str]:
        """Maps chunk id -> already-indexed source_hash, for the ids that exist.

        Used to skip re-embedding chunks whose text hasn't changed since the
        last ingest run (see engine.index_chunks).
        """
        if not chunk_ids:
            return {}
        points = self.client.retrieve(collection_name=self.collection, ids=chunk_ids, with_payload=["source_hash"])
        return {str(point.id): point.payload.get("source_hash", "") for point in points}

    def get_chunks_by_madde(self, kanun_no: str, madde_no: int) -> list[LegislationChunk]:
        """All chunks belonging to one madde — used by [4] Parent Document
        Retrieval to reconstruct the full article text from its child
        chunks (whatever they currently are; always in sync with the index,
        no separate parent-text storage to go stale)."""
        points, _ = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="kanun_no", match=MatchValue(value=kanun_no)),
                    FieldCondition(key="madde_no", match=MatchValue(value=madde_no)),
                ]
            ),
            limit=256,
            with_payload=True,
        )
        chunks = []
        for point in points:
            payload = point.payload
            metadata = ChunkMetadata(
                kanun_no=payload["kanun_no"], kanun_adi=payload["kanun_adi"], madde_no=payload.get("madde_no"),
                fikra_no=payload.get("fikra_no"), bent=payload.get("bent"), kaynak_url=payload.get("kaynak_url", ""),
                source_hash=payload.get("source_hash", ""), durum=payload.get("durum", "yürürlükte"),
            )
            chunks.append(LegislationChunk(id=str(point.id), text=payload["text"], metadata=metadata, citation=payload["citation"]))
        chunks.sort(key=lambda c: (c.metadata.fikra_no is None, c.metadata.fikra_no or 0, c.metadata.bent or ""))
        return chunks

    def delete_by_kanun_no(self, kanun_no: str) -> None:
        self.client.delete(
            collection_name=self.collection,
            points_selector=Filter(must=[FieldCondition(key="kanun_no", match=MatchValue(value=kanun_no))]),
        )

    def scroll_all_chunks(self, batch_size: int = 256) -> list[LegislationChunk]:
        """All chunks currently in the collection — used to (re)build the
        in-memory BM25 sparse index (see pipeline/bm25_index.py), which
        shares this same chunk_id space since Qdrant has no native BM25."""
        chunks: list[LegislationChunk] = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                payload = point.payload
                metadata = ChunkMetadata(
                    kanun_no=payload["kanun_no"], kanun_adi=payload["kanun_adi"], madde_no=payload.get("madde_no"),
                    fikra_no=payload.get("fikra_no"), bent=payload.get("bent"), kaynak_url=payload.get("kaynak_url", ""),
                    source_hash=payload.get("source_hash", ""), durum=payload.get("durum", "yürürlükte"),
                )
                chunks.append(LegislationChunk(id=str(point.id), text=payload["text"], metadata=metadata, citation=payload["citation"]))
            if offset is None:
                break
        return chunks

    def search(self, query_vector: list[float], top_k: int) -> list[RetrievalResult]:
        hits = self.client.query_points(collection_name=self.collection, query=query_vector, limit=top_k, with_payload=True).points
        results = []
        for hit in hits:
            payload = hit.payload
            metadata = ChunkMetadata(
                kanun_no=payload["kanun_no"], kanun_adi=payload["kanun_adi"], madde_no=payload.get("madde_no"),
                fikra_no=payload.get("fikra_no"), bent=payload.get("bent"), kaynak_url=payload.get("kaynak_url", ""),
                source_hash=payload.get("source_hash", ""), durum=payload.get("durum", "yürürlükte"),
            )
            chunk = LegislationChunk(id=str(hit.id), text=payload["text"], metadata=metadata, citation=payload["citation"])
            results.append(RetrievalResult(chunk=chunk, score=hit.score))
        return results
