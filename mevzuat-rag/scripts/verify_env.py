#!/usr/bin/env python3
"""First command to run on a new machine/container:

    python -m scripts.verify_env
    # or: python scripts/verify_env.py

Checks: resolved device, VRAM (if CUDA), embedding model reachable/cached,
Qdrant reachable (local or remote per config), embedding dimension matches
the config, disk space under DATA_DIR. Prints a clear PASS/FAIL/WARN per
check and exits non-zero if anything FAILs — never a silent partial setup.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mevzuat_rag.config import RAGConfig  # noqa: E402
from mevzuat_rag.device import resolve_device  # noqa: E402

MIN_FREE_DISK_GB = 2.0

results: list[tuple[str, str, str]] = []  # (check, status, detail)


def _check(name: str, ok: bool | None, detail: str) -> None:
    status = "PASS" if ok is True else ("WARN" if ok is None else "FAIL")
    results.append((name, status, detail))


def main() -> int:
    config = RAGConfig.from_env()

    device = resolve_device()
    _check("device", True, f"{device} (profile={config.profile})")

    if device == "cuda":
        try:
            import torch

            free_bytes, total_bytes = torch.cuda.mem_get_info()
            free_gb = free_bytes / (1024**3)
            _check("cuda_vram", free_gb >= 1.0, f"{free_gb:.1f} GB boş / {total_bytes / (1024**3):.1f} GB toplam")
        except Exception as exc:
            _check("cuda_vram", False, f"VRAM sorgulanamadı: {exc}")

    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(config.embedding_model, device=device)
        get_dim = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
        actual_dim = get_dim()
        _check(
            "embedding_model",
            actual_dim == config.embedding_dim,
            f"{config.embedding_model} yüklendi, boyut={actual_dim} (config: {config.embedding_dim})",
        )
    except Exception as exc:
        _check("embedding_model", False, f"{config.embedding_model} yüklenemedi: {exc}")

    if config.rerank.enabled:
        try:
            from sentence_transformers import CrossEncoder

            CrossEncoder(config.rerank.model, device=device)
            _check("reranker_model", True, f"{config.rerank.model} yüklendi")
        except Exception as exc:
            _check("reranker_model", None, f"{config.rerank.model} yüklenemedi ({exc}) — graceful degradation devrede, hybrid skorlarıyla çalışır")

    try:
        from mevzuat_rag.store import QdrantStore

        store = QdrantStore(
            collection=config.qdrant_collection,
            url=config.qdrant_url,
            local_path=config.qdrant_local_path,
            embedding_model=config.embedding_model,
            embedding_dim=config.embedding_dim,
        )
        store.client.get_collections()
        target = config.qdrant_url or config.qdrant_local_path
        _check("qdrant", True, f"erişilebilir ({target})")
    except Exception as exc:
        target = config.qdrant_url or config.qdrant_local_path
        _check("qdrant", False, f"Qdrant erişilemedi ({target}): {exc}. QDRANT_URL'i kontrol edin.")

    if config.generation.provider == "deepseek":
        import os

        has_key = bool(os.environ.get("DEEPSEEK_API_KEY"))
        _check("deepseek_api_key", has_key or None, "DEEPSEEK_API_KEY tanımlı" if has_key else "DEEPSEEK_API_KEY tanımlı değil — yalnızca retrieve() çalışır, ask() çalışmaz")

    data_dir = Path(config.qdrant_local_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(data_dir).free / (1024**3)
    _check("disk_space", free_gb >= MIN_FREE_DISK_GB, f"{free_gb:.1f} GB boş ({data_dir})")

    print(f"\n=== verify_env sonuçları (profil: {config.profile}) ===")
    has_fail = False
    for name, status, detail in results:
        print(f"  [{status:4}] {name}: {detail}")
        if status == "FAIL":
            has_fail = True

    if has_fail:
        print("\nEn az bir kontrol FAIL — yukarıdaki mesajlara göre düzeltip tekrar çalıştırın.")
        return 1
    print("\nTüm zorunlu kontroller geçti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
