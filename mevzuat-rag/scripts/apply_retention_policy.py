"""[5] Güvenlik — PII redaksiyonu sonrası veri saklama/silme politikası.

Uygulaması: docs/IMPROVEMENT_IDEAS.md, "3. Güvenlik, Gizlilik ve Uyumluluk"
bölümü, madde 5. ``mevzuat_rag/retention.py``'deki ``delete_older_than`` /
``list_retention_candidates`` fonksiyonlarını çalıştıran CLI.

VARSAYILAN MOD DRY-RUN'DIR. Hiçbir şey silinmez, yalnızca aday listesi
yazdırılır. Gerçekten silmek için ``--confirm`` ZORUNLUDUR — bu, yanlışlıkla
(örn. cron/otomasyon hatası, yanlış --days değeri) veri silinmesini önlemek
için bilinçli bir güvenlik önlemidir, atlanmamalıdır.

    python scripts/apply_retention_policy.py --days 365
    python scripts/apply_retention_policy.py --days 365 --confirm
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mevzuat_rag.config import RAGConfig  # noqa: E402
from mevzuat_rag.retention import delete_older_than, list_retention_candidates  # noqa: E402
from mevzuat_rag.store import QdrantStore  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "İndekslenmiş chunk'lara saklama süresi/silme politikası uygular. "
            "Varsayılan dry-run'dır; gerçekten silmek için --confirm gerekir."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--days",
        type=int,
        required=True,
        help="Bu günden eski (indexed_at bazlı) chunk'lar silme adayı sayılır (zorunlu).",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Hedef koleksiyon adı. Verilmezse RAGConfig.from_env()'deki varsayılan kullanılır.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="(Varsayılan) Hiçbir şey silmeden aday listesini yazdırır.",
    )
    mode.add_argument(
        "--confirm",
        action="store_true",
        help="Gerçekten siler. --dry-run'ı geçersiz kılar. Geri alınamaz.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.days <= 0:
        parser.error("--days pozitif bir sayı olmalıdır.")

    config = RAGConfig.from_env()
    collection = args.collection or config.qdrant_collection

    store = QdrantStore(
        collection=collection,
        url=config.qdrant_url,
        local_path=config.qdrant_local_path,
    )

    really_delete = args.confirm

    if not really_delete:
        candidates = list_retention_candidates(store, args.days)
        print(f"--- Kuru çalışma (hiçbir şey silinmedi) — koleksiyon: {collection} ---")
        print(f"{args.days} günden eski/indexed_at'i olmayan chunk sayısı: {len(candidates)}")
        for c in candidates:
            print(f"  id={c['id']} kanun_no={c['kanun_no']} madde_no={c['madde_no']} indexed_at={c['indexed_at']}")
        if candidates:
            print("\nGerçekten silmek için aynı komutu --confirm ile çalıştırın.")
        return 0

    deleted = delete_older_than(store, args.days)
    print(f"Koleksiyon '{collection}': {deleted} chunk silindi (indexed_at > {args.days} gün).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nİşlem kullanıcı tarafından kesildi.")
        sys.exit(130)
