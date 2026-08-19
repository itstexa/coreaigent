"""Dense embedding wrapper — deliberately the same pattern as
``insangram/src/rag/embed.py``: plain ``sentence-transformers`` BGE-M3,
dense-only, cosine similarity. No sparse vectors, no reranker — that stack is
already proven to work and isn't being changed for this service.
"""
from __future__ import annotations

import logging
import math
import os
import time
from typing import TYPE_CHECKING

from sentence_transformers import SentenceTransformer

from mevzuat_rag.errors import (
    EmbeddingComputeError,
    EmbeddingDimensionError,
    EmbeddingInputError,
    EmbeddingModelLoadError,
    EmbeddingOOMError,
)

if TYPE_CHECKING:
    from mevzuat_rag.config import EmbeddingConfig

logger = logging.getLogger(__name__)

_model_cache: dict[str, SentenceTransformer] = {}
_default_config: "EmbeddingConfig | None" = None


def _get_default_config() -> "EmbeddingConfig":
    global _default_config
    if _default_config is None:
        from mevzuat_rag.config import RAGConfig

        _default_config = RAGConfig.load().embedding
    return _default_config


def _model_name(model: SentenceTransformer) -> str:
    return getattr(model, "model_name", None) or getattr(model, "_model_name", None) or "unknown"


def _base_context(model: SentenceTransformer, texts: list[str] | None, batch_size: int) -> dict:
    return {
        "batch_size": batch_size,
        "text_count": len(texts) if texts is not None else 0,
        "model_name": _model_name(model),
        "device": str(getattr(model, "device", None)),
        "first_text_chars": (texts[0][:80] if texts else None),
    }


def _expected_dim(model: SentenceTransformer, config: "EmbeddingConfig") -> int:
    if config.dim:
        return config.dim
    return int(model.get_sentence_embedding_dimension())


def _is_oom_error(exc: Exception) -> bool:
    return "out of memory" in str(exc).lower()


def _is_transient_error(exc: Exception) -> bool:
    text = str(exc).lower()
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    return any(key in text for key in ("timeout", "connection", "temporarily", "try again"))


def _validate_texts(texts: list[str] | None, config: "EmbeddingConfig") -> list[str]:
    if texts is None or len(texts) == 0:
        raise EmbeddingInputError(
            "embed_texts en az bir metin bekler.",
            context={"text_count": 0},
        )

    for idx, text in enumerate(texts):
        if text is None:
            raise EmbeddingInputError(
                f"Girdi listesinde {idx}. öğe None.",
                context={"index": idx},
            )
        if not text.strip():
            raise EmbeddingInputError(
                f"Girdi listesinde {idx}. metin boş veya yalnızca boşluk içeriyor.",
                context={"index": idx},
            )

    return texts


def _check_overlong(texts: list[str], config: "EmbeddingConfig") -> None:
    if config.max_input_chars <= 0:
        return

    over = [(idx, len(text)) for idx, text in enumerate(texts) if len(text) > config.max_input_chars]
    if not over:
        return

    max_len = max(length for _, length in over)

    if config.on_overlong == "error":
        raise EmbeddingInputError(
            f"Embedding girişinde {len(over)} metin max_input_chars={config.max_input_chars} eşiğini aşıyor; "
            f"en uzun metin {max_len} karakter.",
            context={
                "over_count": len(over),
                "max_input_chars": config.max_input_chars,
                "max_len": max_len,
            },
        )

    logger.warning(
        "Embedding girişinde %d metin max_input_chars=%d eşiğini aşıyor; en uzun metin %d karakter. "
        "Model/tokenizer seviyesinde kesilebilir.",
        len(over),
        config.max_input_chars,
        max_len,
    )


def get_embedder(model_name: str, device: str) -> SentenceTransformer:
    key = f"{model_name}::{device}"
    if key in _model_cache:
        return _model_cache[key]

    start = time.perf_counter()
    hf_home = os.environ.get("HF_HOME")

    try:
        model = SentenceTransformer(model_name, device=device)
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.warning(
            "Embedding model yüklenemedi: %s (device=%s, HF_HOME=%s) — %.3fs",
            model_name,
            device,
            hf_home,
            elapsed,
        )
        raise EmbeddingModelLoadError(
            f"Embedding model yüklenemedi: {model_name} (device={device}, HF_HOME={hf_home}). "
            "Model adını, cache dizinini, ağ bağlantısını ve CUDA/ROCm sürücüsünü kontrol edin.",
            cause=e,
            context={
                "model_name": model_name,
                "device": device,
                "hf_home": hf_home,
                "elapsed_s": round(elapsed, 3),
            },
        ) from e

    elapsed = time.perf_counter() - start
    logger.info("Embedding model yüklendi: %s (device=%s) — %.3fs", model_name, device, elapsed)
    _model_cache[key] = model
    return model


def _embed_texts_with_config(
    model: SentenceTransformer,
    texts: list[str],
    config: "EmbeddingConfig",
) -> list[list[float]]:
    validated = _validate_texts(texts, config)
    _check_overlong(validated, config)

    batch_size = max(1, config.batch_size)
    transient_attempts = 0

    while True:
        context = _base_context(model, validated, batch_size)

        try:
            vectors = model.encode(
                validated,
                batch_size=batch_size,
                normalize_embeddings=True,
            )
        except Exception as e:
            if _is_oom_error(e) and config.oom_retry and batch_size > config.min_batch_size:
                new_batch = max(batch_size // 2, config.min_batch_size)
                logger.warning(
                    "Embedding encode sırasında OOM; batch_size=%s -> %s",
                    batch_size,
                    new_batch,
                )
                batch_size = new_batch
                continue

            if _is_transient_error(e) and transient_attempts < config.max_retries:
                delay = 0.5 * (2 ** transient_attempts)
                logger.warning(
                    "Geçici embedding hatası (%s); retry %s/%s, %.1fs sonra...",
                    type(e).__name__,
                    transient_attempts + 1,
                    config.max_retries,
                    delay,
                )
                time.sleep(delay)
                transient_attempts += 1
                continue

            if _is_oom_error(e):
                raise EmbeddingOOMError(
                    f"Embedding encode OOM hatası; batch_size={batch_size}, "
                    f"min_batch_size={config.min_batch_size}.",
                    cause=e,
                    context=context,
                ) from e

            raise EmbeddingComputeError(
                "Embedding encode sırasında beklenmeyen hata.",
                cause=e,
                context=context,
            ) from e

        vectors_list = [v.tolist() for v in vectors]

        if config.strict_validation:
            validate_embeddings(
                vectors_list,
                len(validated),
                _expected_dim(model, config),
                check_normalized=True,
            )

        return vectors_list


def embed_texts_with_config(
    model: SentenceTransformer,
    texts: list[str],
    *,
    config: "EmbeddingConfig",
) -> list[list[float]]:
    """Config-aware variant used by engine.index_chunks.

    Keeps the public ``embed_texts`` wrapper backward compatible while giving
    the engine an explicit path for its already-loaded configuration.
    """
    return _embed_texts_with_config(model, texts, config)


def embed_texts(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    """Public entry point; uses default profile embedding config."""
    return _embed_texts_with_config(model, texts, _get_default_config())


def _embed_query_with_config(
    model: SentenceTransformer,
    query: str,
    config: "EmbeddingConfig",
) -> list[float]:
    if not isinstance(query, str) or not query.strip():
        raise EmbeddingInputError(
            "embed_query boş veya string olmayan bir sorgu kabul etmiyor.",
            context={"query_type": type(query).__name__},
        )

    if config.max_input_chars > 0 and len(query) > config.max_input_chars:
        if config.on_overlong == "error":
            raise EmbeddingInputError(
                f"Sorgu max_input_chars={config.max_input_chars} eşiğini aşıyor: {len(query)} karakter.",
                context={"query_len": len(query), "max_input_chars": config.max_input_chars},
            )

        logger.warning(
            "Sorgu max_input_chars=%d eşiğini aşıyor: %d karakter. Tokenizer kesebilir.",
            config.max_input_chars,
            len(query),
        )

    transient_attempts = 0

    while True:
        context = _base_context(model, [query], 1)

        try:
            vector = model.encode(query, batch_size=1, normalize_embeddings=True).tolist()
        except Exception as e:
            if _is_transient_error(e) and transient_attempts < config.max_retries:
                delay = 0.5 * (2 ** transient_attempts)
                logger.warning(
                    "Geçici embedding sorgu hatası (%s); retry %s/%s, %.1fs sonra...",
                    type(e).__name__,
                    transient_attempts + 1,
                    config.max_retries,
                    delay,
                )
                time.sleep(delay)
                transient_attempts += 1
                continue

            if _is_oom_error(e):
                raise EmbeddingOOMError(
                    "Embedding sorgu encode OOM hatası.",
                    cause=e,
                    context=context,
                ) from e

            raise EmbeddingComputeError(
                "Embedding sorgu encode sırasında beklenmeyen hata.",
                cause=e,
                context=context,
            ) from e

        if config.strict_validation:
            validate_embeddings([vector], 1, _expected_dim(model, config), check_normalized=True)

        return vector


def embed_query(model: SentenceTransformer, query: str) -> list[float]:
    """Public entry point; uses default profile embedding config."""
    return _embed_query_with_config(model, query, _get_default_config())


def validate_embeddings(
    vectors: list[list[float]],
    expected_count: int,
    expected_dim: int,
    *,
    check_normalized: bool = True,
) -> None:
    """Central embedding output validation.

    Kept here so both ingest and query paths validate identically; sensitive
    checks can be disabled via ``strict_validation`` at call sites.
    """
    if len(vectors) != expected_count:
        raise EmbeddingDimensionError(
            f"Embedding satır sayısı {len(vectors)}, beklenen {expected_count}.",
            context={"actual_count": len(vectors), "expected_count": expected_count},
        )

    for idx, vector in enumerate(vectors):
        if len(vector) != expected_dim:
            raise EmbeddingDimensionError(
                f"Embedding vektörü {idx} boyutu {len(vector)}, beklenen {expected_dim}.",
                context={"index": idx, "actual_dim": len(vector), "expected_dim": expected_dim},
            )

        for value in vector:
            if not math.isfinite(value):
                raise EmbeddingComputeError(
                    f"Embedding vektörü {idx} içinde NaN/Inf değer var.",
                    context={"index": idx},
                )

        if check_normalized:
            norm = math.sqrt(sum(value * value for value in vector))
            if abs(norm - 1.0) > 1e-3:
                raise EmbeddingComputeError(
                    f"Embedding vektörü {idx} normalize değil (L2 norm={norm:.6f}).",
                    context={"index": idx, "l2_norm": norm},
                )
