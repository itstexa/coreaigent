"""Embedding modeli değişikliğinde mevcut koleksiyonu yeni koleksiyona taşır.

Eski koleksiyona ASLA yazmaz. Yarıda kesilse de eski index bozulmaz; bu script
yalnızca yeni koleksiyon oluşturur/doldurur. Prod'a geçiş kullanıcının yeni
koleksiyonu ``QDRANT_COLLECTION_MEVZUAT`` ile işaret etmesiyle olur.

    python scripts/reembed.py --collection mevzuat_chunks --new-model BAAI/bge-m3 --dry-run
    python scripts/reembed.py --collection mevzuat_chunks --new-model BAAI/bge-m3
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mevzuat_rag.config import RAGConfig  # noqa: E402
from mevzuat_rag.embedding import embed_texts, get_embedder  # noqa: E402
from mevzuat_rag.store import QdrantStore  # noqa: E402


def _meta_path(config: RAGConfig, collection: str) -> Path:
    """QdrantStore ile aynı meta dosyası; eski model/dim kaydını bulmak için."""
    return Path(config.qdrant_local_path) / f"index_meta_{collection}.json"


def _read_source_meta(config: RAGConfig, collection: str) -> tuple[str, int]:
    """Mevcut koleksiyonun kayıtlı model/dim bilgisini döner.

    Config zaten yeni modele geçmiş olabilir; eski koleksiyonu doğru açmak
    için meta dosyasındaki eski model/dim bilgisini kullanmak gerekir.
    """
    path = _meta_path(config, collection)
    if not path.exists():
        return config.embedding_model, config.embedding_dim

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        data = {}

    return (
        str(data.get("embedding_model", config.embedding_model)),
        int(data.get("embedding_dim", config.embedding_dim)),
    )


def _human_bytes(n: int) -> str:
    """Disk tahminlerini insan okunur hale getirir."""
    amount = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{n} B"


def _validate_batch_vectors(
    vectors: list[list[float]],
    expected_count: int,
    expected_dim: int,
) -> None:
    """Yeni modelden dönen vektörlerin boyut/sayı olarak tipe uygunluğunu denetler."""
    if len(vectors) != expected_count:
        raise RuntimeError(
            f"Embedding sayısı uyuşmuyor: beklenen {expected_count}, dönen {len(vectors)}"
        )
    if any(len(v) != expected_dim for v in vectors):
        raise RuntimeError(
            f"Embedding boyutu uyuşmuyor: bazı vektörler {expected_dim} boyutlu değil"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Mevcut Qdrant koleksiyonunu yeni embedding modeliyle yeniden indeksler. "
            "Eski koleksiyon silinmez ve değiştirilmez; yalnızca yeni koleksiyon yazılır."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--collection",
        required=True,
        help="Mevcut kaynak koleksiyon adı (zorunlu).",
    )
    parser.add_argument(
        "--new-model",
        required=True,
        help="Yeni embedding model adı, ör. BAAI/bge-m3 (zorunlu).",
    )
    parser.add_argument(
        "--new-dim",
        type=int,
        default=None,
        help="Yeni embedding boyutu. Verilmezse modelin get_sentence_embedding_dimension() kullanılır.",
    )
    parser.add_argument(
        "--new-collection",
        default=None,
        help="Yeni koleksiyon adı. Varsayılan: <collection>_v2.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Hiçbir koleksiyon oluşturmadan/yazmadan tahmin raporu çıkarır.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="Yeniden embedding sırasında kullanılacak batch boyutu.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.batch_size <= 0:
        parser.error("--batch-size pozitif bir sayı olmalıdır.")
    if args.new_dim is not None and args.new_dim <= 0:
        parser.error("--new-dim pozitif bir sayı olmalıdır.")

    config = RAGConfig.from_env()
    new_collection = args.new_collection or f"{args.collection}_v2"

    if new_collection == args.collection:
        parser.error(
            "--new-collection, mevcut --collection ile aynı olamaz; "
            "eski koleksiyon hiçbir koşulda değiştirilmez."
        )

    old_model, old_dim = _read_source_meta(config, args.collection)

    source = QdrantStore(
        collection=args.collection,
        url=config.qdrant_url,
        local_path=config.qdrant_local_path,
        embedding_model=old_model,
        embedding_dim=old_dim,
    )

    chunks = source.scroll_all_chunks()
    old_count = len(chunks)
    # Embedded/local Qdrant only allows one QdrantClient on a given storage
    # path at a time — even for two different collections in that same path.
    # We already have every chunk in memory, so close the source connection
    # before opening the destination one (avoids "storage folder is already
    # accessed by another instance" when qdrant_url is unset / local mode).
    source.client.close()

    if not chunks:
        print("Mevcut koleksiyonda chunk yok; yapılacak işlem yok.")
        return 0

    model = get_embedder(args.new_model, config.embedding_device)

    new_dim = args.new_dim
    if new_dim is None:
        new_dim = model.get_sentence_embedding_dimension()

    total_batches = math.ceil(len(chunks) / args.batch_size)

    if args.dry_run:
        sample_size = min(args.batch_size, len(chunks))
        sample_chunks = chunks[:sample_size]

        t0 = time.perf_counter()
        embed_texts(model, [c.text for c in sample_chunks])
        sample_batch_time = time.perf_counter() - t0

        estimated_seconds = total_batches * sample_batch_time
        disk_bytes = len(chunks) * new_dim * 4 * 2  # float32 + 2x güvenlik payı

        print("--- Kuru çalışma (hiçbir koleksiyon oluşturulmadı / yazılmadı) ---")
        print(f"Eski koleksiyon: {args.collection}")
        print(f"Hedef koleksiyon: {new_collection}")
        print(f"Chunk sayısı: {len(chunks)}")
        print(f"Yeni model: {args.new_model}")
        print(f"Yeni embedding boyutu: {new_dim}")
        print(f"Batch boyutu: {args.batch_size}")
        print(f"Toplam batch sayısı: {total_batches}")
        print(f"Örnek batch embed süresi ({sample_size} chunk): {sample_batch_time:.2f}s")
        print(f"Tahmini toplam embed süresi: {estimated_seconds:.2f}s")
        print(f"Tahmini disk ihtiyacı (2x güvenlik payıyla): {_human_bytes(disk_bytes)}")
        return 0

    destination = QdrantStore(
        collection=new_collection,
        url=config.qdrant_url,
        local_path=config.qdrant_local_path,
        embedding_model=args.new_model,
        embedding_dim=new_dim,
    )

    for batch_idx in range(total_batches):
        start = batch_idx * args.batch_size
        batch = chunks[start : start + args.batch_size]

        vectors = embed_texts(model, [c.text for c in batch])
        _validate_batch_vectors(vectors, len(batch), new_dim)

        destination.upsert_chunks(batch, vectors)
        print(f"[{batch_idx + 1}/{total_batches}] {start + len(batch)}/{len(chunks)} chunk yazıldı")

    new_count = destination.client.count(collection_name=new_collection).count

    if old_count != new_count:
        raise RuntimeError(
            f"Chunk sayısı doğrulanamadı: eski koleksiyon={old_count}, "
            f"yeni koleksiyon={new_count}"
        )

    print(
        f"Yeni koleksiyon '{new_collection}' hazır ve doğrulandı ({new_count} chunk). "
        f"Prod'a almak için QDRANT_COLLECTION_MEVZUAT={new_collection} ayarlayın. "
        f"Eski koleksiyon '{args.collection}' silinmedi, dokunulmadı."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nİşlem kullanıcı tarafından kesildi. Eski koleksiyon değiştirilmedi.")
        sys.exit(130)
    except Exception as exc:
        print(f"\nHATA: {exc}")
        print("Eski koleksiyon değiştirilmedi; yeni koleksiyon kısmen yazılmış olabilir.")
        sys.exit(1)
