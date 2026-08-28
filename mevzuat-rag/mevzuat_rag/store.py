"""Qdrant-backed storage for legislation chunks.

Named dense ("dense", BGE-M3 cosine) + named sparse ("bm25", Modifier.IDF)
vector per point — Qdrant IS the hybrid index now (bkz. pipeline/sparse_vector.py).
Eskiden yalnızca unnamed dense vektör vardı ve BM25 ayrı, RAM'de tutulan bir
``rank_bm25`` index'iydi (pipeline/bm25_index.py) — o index kendi
docstring'inde "a few thousand chunks at most" diyordu, 1M-dosya hedefiyle
çelişiyordu (denetim bulgusu, bkz. rag_config_panel.py madde 4). Supports
either a remote Qdrant server (``QDRANT_URL``, used by ``compose.yaml``'s
``qdrant`` service) or an embedded on-disk client (``QDRANT_LOCAL_PATH``,
useful for the smoke test and local dev without Docker).

Fail-fast on embedding mismatch: a small ``index_meta_{collection}.json``
next to the local Qdrant data records which embedding model/dimension built
the index. Opening an existing collection with a different model/dim raises
immediately instead of silently returning wrong-dimension nonsense results
later. See DEPLOY.md / MIGRATION.md.

GERİYE DÖNÜK UYUMSUZ: bu named-vector şeması, migration öncesi (unnamed
dense vektörlü) bir koleksiyonla uyumlu DEĞİL. Var olan bir koleksiyon
açılırken "dense" adlı vektör bulunamazsa ``IndexMetadataMismatch``
fırlatılır — eski koleksiyonu bu şemaya taşımak için ``scripts/reembed.py``
kullanın (yeni koleksiyona geçiş, eskisine dokunmaz).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    Modifier,
    PointStruct,
    SparseVectorParams,
    VectorParams,
)

from mevzuat_rag.models import ChunkMetadata, LegislationChunk, RetrievalResult
from mevzuat_rag.pipeline.sparse_vector import text_to_sparse_vector

_DENSE_VECTOR_NAME = "dense"
_SPARSE_VECTOR_NAME = "bm25"


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
                vectors_config={_DENSE_VECTOR_NAME: VectorParams(size=self.embedding_dim, distance=Distance.COSINE)},
                sparse_vectors_config={_SPARSE_VECTOR_NAME: SparseVectorParams(modifier=Modifier.IDF)},
            )

    def point_count(self) -> int:
        """Koleksiyondaki toplam nokta (chunk) sayısı — dynamic_profile.py'nin
        KÜÇÜK/ORTA/BÜYÜK korpus profili seçimi için. ``exact=False``: hızlı
        yaklaşık sayım yeterli, her sorguda çağrılıyor (tam sayım gereksiz
        maliyet)."""
        return self.client.count(collection_name=self.collection, exact=False).count

    def _check_index_metadata(self) -> None:
        collection_info = self.client.get_collection(self.collection)
        dense_params = collection_info.config.params.vectors.get(_DENSE_VECTOR_NAME) if isinstance(collection_info.config.params.vectors, dict) else None
        if dense_params is None:
            raise IndexMetadataMismatch(
                f"Koleksiyon '{self.collection}' bu paketin beklediği "
                f"'{_DENSE_VECTOR_NAME}'/'{_SPARSE_VECTOR_NAME}' adlı named-vector "
                f"şemasıyla uyuşmuyor (muhtemelen BM25-native-sparse migration'ından "
                f"ÖNCE oluşturulmuş, unnamed-vector'lü eski bir koleksiyon). Bu "
                f"koleksiyonu doğrudan açmak yerine scripts/reembed.py ile yeni "
                f"şemalı bir koleksiyona taşıyın — bkz. MIGRATION.md."
            )
        actual_dim = dense_params.size
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
        # "indexed_at" (ISO-8601 UTC) — saklama/silme politikasının (bkz.
        # retention.py) dayandığı çapa: bu kayıt olmadan "bu veri ne kadar
        # eski" sorusuna sonradan cevap verilemez, KVKK'nın "amaç sona
        # erince sil" ilkesi vatandaş belgesinden türeyen içerik için
        # uygulanamaz hale gelir.
        indexed_at = datetime.now(timezone.utc).isoformat()
        points = [
            PointStruct(
                id=chunk.id,
                vector={
                    _DENSE_VECTOR_NAME: vector,
                    _SPARSE_VECTOR_NAME: text_to_sparse_vector(chunk.text),
                },
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
                    "indexed_at": indexed_at,
                    "mevzuat_turu": chunk.metadata.mevzuat_turu,
                    "contains_table": chunk.metadata.contains_table,
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
                mevzuat_turu=payload.get("mevzuat_turu", "kanun"), contains_table=payload.get("contains_table", False),
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
                mevzuat_turu=payload.get("mevzuat_turu", "kanun"), contains_table=payload.get("contains_table", False),
                )
                chunks.append(LegislationChunk(id=str(point.id), text=payload["text"], metadata=metadata, citation=payload["citation"]))
            if offset is None:
                break
        return chunks

    def search(self, query_vector: list[float], top_k: int) -> list[RetrievalResult]:
        hits = self.client.query_points(
            collection_name=self.collection, query=query_vector, using=_DENSE_VECTOR_NAME, limit=top_k, with_payload=True
        ).points
        results = []
        for hit in hits:
            payload = hit.payload
            metadata = ChunkMetadata(
                kanun_no=payload["kanun_no"], kanun_adi=payload["kanun_adi"], madde_no=payload.get("madde_no"),
                fikra_no=payload.get("fikra_no"), bent=payload.get("bent"), kaynak_url=payload.get("kaynak_url", ""),
                source_hash=payload.get("source_hash", ""), durum=payload.get("durum", "yürürlükte"),
                mevzuat_turu=payload.get("mevzuat_turu", "kanun"), contains_table=payload.get("contains_table", False),
            )
            chunk = LegislationChunk(id=str(hit.id), text=payload["text"], metadata=metadata, citation=payload["citation"])
            results.append(RetrievalResult(chunk=chunk, score=hit.score))
        return results

    def search_sparse(self, query_text: str, top_k: int) -> list[RetrievalResult]:
        """BM25-style native sparse arama — eski in-memory ``BM25Index``'in
        yerini alır (bkz. pipeline/bm25_index.py). Sorgu boşsa/tokenize
        edilemiyorsa (ör. yalnızca stopword) Qdrant'a hiç gitmeden boş liste
        döner — boş sparse vektörle sorgu atmak anlamsız ve gereksiz bir
        round-trip olurdu."""
        query_vector = text_to_sparse_vector(query_text)
        if not query_vector.indices:
            return []
        hits = self.client.query_points(
            collection_name=self.collection, query=query_vector, using=_SPARSE_VECTOR_NAME, limit=top_k, with_payload=True
        ).points
        results = []
        for hit in hits:
            payload = hit.payload
            metadata = ChunkMetadata(
                kanun_no=payload["kanun_no"], kanun_adi=payload["kanun_adi"], madde_no=payload.get("madde_no"),
                fikra_no=payload.get("fikra_no"), bent=payload.get("bent"), kaynak_url=payload.get("kaynak_url", ""),
                source_hash=payload.get("source_hash", ""), durum=payload.get("durum", "yürürlükte"),
                mevzuat_turu=payload.get("mevzuat_turu", "kanun"), contains_table=payload.get("contains_table", False),
            )
            chunk = LegislationChunk(id=str(hit.id), text=payload["text"], metadata=metadata, citation=payload["citation"])
            results.append(RetrievalResult(chunk=chunk, score=hit.score))
        return results
