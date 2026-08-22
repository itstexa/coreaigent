#!/usr/bin/env python3
"""GPU doygunluk noktasını ölçen tek-seferlik embedding batch_size kalibrasyonu.

``docs/IMPROVEMENT_IDEAS.md`` — "4. Ölçek ve Performans, #3: Embedding
batch_size otomatik kalibrasyon" fikrinin uygulaması. ``config.py``'deki
``EmbeddingConfig.batch_size`` şu an sabit 32 — hiç ölçülmeden seçilmiş.
``embedding.py``'deki ``embed_texts_with_config`` zaten OOM durumunda
batch_size'ı otomatik yarıya indiren bir mekanizmaya (``oom_retry``) sahip,
ama YUKARI doğru — hangi batch_size en yüksek verimi veriyor — hiç kalibre
edilmemişti. 1M chunk'lık bir ingest'te doğru batch_size, toplam ingest
süresini ciddi ölçüde kısaltabilir.

Kullanım:
    python scripts/calibrate_embedding_batch.py
    python scripts/calibrate_embedding_batch.py --quick
    python scripts/calibrate_embedding_batch.py --batch-sizes 16,32,64 --samples 256

Bu script ``config/default.yaml``'ı OTOMATİK DEĞİŞTİRMEZ — yalnızca önerilen
batch_size'ı konsola yazdırır; uygulamak isteyip istemediğine kullanıcı
manuel karar verir (bu depodaki disiplin: config değişiklikleri elle,
gerekçeli yapılır, bkz. reembed.py / verify_env.py).
"""
from __future__ import annotations

import argparse
import itertools
import re
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mevzuat_rag.config import EmbeddingConfig, RAGConfig  # noqa: E402
from mevzuat_rag.embedding import embed_texts_with_config, get_embedder  # noqa: E402
from mevzuat_rag.errors import EmbeddingOOMError  # noqa: E402

DEFAULT_BATCH_SIZES = [8, 16, 32, 64, 128, 256]
QUICK_BATCH_SIZES = [8, 16, 32]
DEFAULT_SAMPLES = 256
QUICK_SAMPLES = 24

SAMPLE_DATA_DIR = Path(__file__).resolve().parents[1] / "sample_data" / "legislation"

# "MADDE 5- ..." kalıbının başladığı yerden bölerek her maddeyi ayrı bir
# örnek metin olarak çıkarır (lookahead — ayraç kendisi de sonuçta kalır).
_MADDE_SPLIT_RE = re.compile(r"(?=MADDE\s+\d+\s*-)")


def extract_madde_texts(sample_dir: Path) -> list[str]:
    """``sample_data/legislation/*.md`` dosyalarından gerçek madde metinlerini çıkarır.

    Lorem ipsum değil — sentetik korpus bu gerçek Türkçe mevzuat cümlelerinin
    tekrarından üretilir, çünkü kalibrasyonun amacı gerçek ingest metinlerine
    yakın uzunluk/tokenizasyon davranışı ölçmek.
    """
    texts: list[str] = []
    for path in sorted(sample_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        body_start = raw.find("MADDE")
        if body_start == -1:
            continue
        body = raw[body_start:]
        parts = [p.strip() for p in _MADDE_SPLIT_RE.split(body) if p.strip()]
        texts.extend(parts)

    if not texts:
        raise RuntimeError(
            f"{sample_dir} altında hiç madde metni bulunamadı; kalibrasyon "
            "için gerçek mevzuat metnine ihtiyaç var."
        )
    return texts


def build_synthetic_corpus(base_texts: list[str], count: int) -> list[str]:
    """Gerçek madde metinlerini döngüsel tekrarla ``count`` boyutunda korpusa çoğaltır."""
    if count <= 0:
        raise ValueError("count pozitif olmalı.")
    cycler = itertools.cycle(base_texts)
    return [next(cycler) for _ in range(count)]


def parse_batch_sizes(raw: str) -> list[int]:
    sizes = [int(x.strip()) for x in raw.split(",") if x.strip()]
    if not sizes:
        raise ValueError("En az bir batch boyutu verilmeli.")
    if any(s <= 0 for s in sizes):
        raise ValueError("Batch boyutları pozitif olmalı.")
    if sorted(sizes) != sizes:
        raise ValueError("--batch-sizes artan sırada verilmeli (ör. 8,16,32,64).")
    return sizes


def is_oom_error(exc: Exception) -> bool:
    """``EmbeddingOOMError``, ``torch.cuda.OutOfMemoryError`` ya da mesajında
    "out of memory" geçen genel ``RuntimeError`` — hepsini OOM sayar."""
    if isinstance(exc, EmbeddingOOMError):
        return True
    try:
        import torch

        if isinstance(exc, torch.cuda.OutOfMemoryError):
            return True
    except ImportError:
        pass
    return "out of memory" in str(exc).lower()


def calibrate(
    model: Any,
    corpus: list[str],
    batch_sizes: list[int],
    base_embedding_config: EmbeddingConfig,
) -> list[dict]:
    """Artan batch boyutlarında chunk/saniye verimini ölçer.

    Her batch boyutu için ``embed_texts_with_config`` çağrılır; iç OOM-retry
    mekanizması bu ölçüm için kapatılır (``oom_retry=False``), çünkü o
    mekanizma sessizce batch_size'ı yarıya indirip ölçümü maskeler — biz
    tam olarak hangi boyutta OOM olduğunu görmek istiyoruz.

    OOM'a çarpınca o batch boyutu atlanır ve döngü DURDURULUR (daha büyük
    boyutlar denenmez — GPU'nun doygunluk noktası geçilmiş demektir).
    Başka bir beklenmeyen hata olursa o boyut atlanır ama döngü devam eder.
    Script hiçbir koşulda exception fırlatıp çökmez.
    """
    results: list[dict] = []

    for batch_size in batch_sizes:
        probe_config = replace(
            base_embedding_config,
            batch_size=batch_size,
            oom_retry=False,
            max_retries=0,
        )

        try:
            start = time.perf_counter()
            embed_texts_with_config(model, corpus, config=probe_config)
            elapsed = time.perf_counter() - start
        except Exception as exc:  # noqa: BLE001 — script asla çökmemeli
            if is_oom_error(exc):
                print(f"  batch_size={batch_size:>4}: OOM — durduruluyor, önceki sonuçlar korunuyor.")
                try:
                    import torch

                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except ImportError:
                    pass
                break

            print(f"  batch_size={batch_size:>4}: beklenmeyen hata ({type(exc).__name__}: {exc}) — atlanıyor.")
            continue

        throughput = len(corpus) / elapsed if elapsed > 0 else float("inf")
        results.append(
            {
                "batch_size": batch_size,
                "elapsed_s": elapsed,
                "throughput_chunks_per_s": throughput,
            }
        )
        print(f"  batch_size={batch_size:>4}: {elapsed:7.2f}s toplam, {throughput:9.1f} chunk/s")

    return results


def best_result(results: list[dict]) -> dict | None:
    if not results:
        return None
    return max(results, key=lambda r: r["throughput_chunks_per_s"])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Embedding batch_size için GPU doygunluk noktasını ölçer. "
            "config/default.yaml'ı değiştirmez, yalnızca öneri yazdırır."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Hızlı doğrulama modu: az sayıda küçük batch boyutu (8,16,32), az örnek.",
    )
    parser.add_argument(
        "--batch-sizes",
        type=str,
        default=None,
        help="Virgülle ayrılmış, artan sıralı batch boyutu listesi (ör. 8,16,32,64,128,256).",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=None,
        help="Her batch boyutu için embed edilecek sentetik metin sayısı.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="RAG_PROFILE ile aynı anlamda; hangi config profilinin (model/device) kullanılacağını belirler.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.batch_sizes:
        try:
            batch_sizes = parse_batch_sizes(args.batch_sizes)
        except ValueError as exc:
            parser.error(str(exc))
            return 2  # pragma: no cover - parser.error() zaten exit eder
    else:
        batch_sizes = QUICK_BATCH_SIZES if args.quick else DEFAULT_BATCH_SIZES

    samples = args.samples or (QUICK_SAMPLES if args.quick else DEFAULT_SAMPLES)
    if samples <= 0:
        parser.error("--samples pozitif bir sayı olmalıdır.")

    config = RAGConfig.load(args.profile)

    print(f"Cihaz: {config.embedding.device}, model: {config.embedding.model}, profil: {config.profile}")
    print(f"Denenecek batch boyutları: {batch_sizes}")
    print(f"Batch başına örnek sayısı: {samples}\n")

    base_texts = extract_madde_texts(SAMPLE_DATA_DIR)
    corpus = build_synthetic_corpus(base_texts, samples)
    print(f"{len(base_texts)} gerçek madde metninden {len(corpus)} örneklik sentetik korpus üretildi.\n")

    try:
        model = get_embedder(config.embedding.model, config.embedding.device)
    except Exception as exc:
        print(f"HATA: embedding modeli yüklenemedi: {exc}")
        return 1

    print("Kalibrasyon başlıyor...")
    results = calibrate(model, corpus, batch_sizes, config.embedding)

    print()
    if not results:
        print("Hiçbir batch boyutu başarıyla ölçülemedi (ilk denemede OOM ya da beklenmeyen hata).")
        print(f"Mevcut config/default.yaml batch_size değeri ({config.embedding.batch_size}) değiştirilmeden korunmalı.")
        return 1

    best = best_result(results)
    print("=== Sonuç ===")
    for r in results:
        marker = "  <- en iyi" if r is best else ""
        print(f"  batch_size={r['batch_size']:>4}: {r['throughput_chunks_per_s']:9.1f} chunk/s{marker}")

    print()
    print(f"Öneri: batch_size={best['batch_size']} (mevcut config/default.yaml: {config.embedding.batch_size})")
    print(
        "Bu script config/default.yaml'ı DEĞİŞTİRMEDİ. Öneriyi uygulamak "
        "isterseniz embedding.batch_size değerini elle güncelleyin — bu "
        "depoda config değişiklikleri elle, gerekçeli yapılır."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nKalibrasyon kullanıcı tarafından kesildi.")
        sys.exit(130)
