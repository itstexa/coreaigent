"""Shared LLM client factory — used by every stage that makes an LLM call
(generation, router, multi-query, HyDE, CRAG, post-hoc-verify). Provider-
agnostic: any backend that speaks the OpenAI chat-completions wire format
works here — DeepSeek's hosted API, or a locally-served model (e.g. Jamba
behind vLLM/TGI/etc.) exposing an OpenAI-compatible endpoint. The actual
provider/credentials/model come from ``RAGConfig.generation`` (resolved
per-provider in config.py's ``_PROVIDER_ENV`` — DEEPSEEK_*/JAMBA_*/generic
LLM_* env vars), not from anything hardcoded in this module.

``create_chat_completion()`` adds capability-aware structured output on top
of the raw client: a stage that wants JSON (router/multi_query/crag/
post_hoc_verify) asks for ``json_mode=True`` and doesn't need to know
whether the backend actually honors ``response_format``. Not every
OpenAI-compatible server does — some (especially minimal local shims in
front of a model like Jamba) reject the unknown field outright. Rather than
trusting a static per-provider assumption (which would crash the call the
moment it's wrong), this probes on first use and remembers the result per
``(base_url, model)`` for the rest of the process — "sistem özelliklerini
tanıyıp ona göre çalışma": the capability is learned once, not guessed.
"""
from __future__ import annotations

import logging
import os
import threading

from openai import OpenAI

logger = logging.getLogger("mevzuat_rag.llm_client")


def get_client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    """``api_key``/``base_url`` should normally come from a resolved
    ``RAGConfig.generation`` (see config.py) so the right provider's
    credentials/endpoint are used. Falls back to raw env vars only for
    callers that construct a client without a config in hand (kept for
    backward compatibility with pre-multi-provider call sites/scripts)."""
    return OpenAI(
        api_key=api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("LLM_API_KEY"),
        base_url=(
            base_url
            or os.environ.get("DEEPSEEK_BASE_URL")
            or os.environ.get("LLM_BASE_URL")
            or "https://api.deepseek.com/v1"
        ),
    )


# (base_url, model) -> None (bilinmiyor, hiç denenmedi) | True (destekliyor)
# | False (reddetti, bir daha denenmeyecek). Process ömrü boyunca yaşar —
# RAGEngine örnekleri arasında paylaşılır, ayrı bir "capability config"
# dosyası/DB'si gerekmez.
_json_mode_support: dict[tuple[str, str], bool] = {}
_json_mode_lock = threading.Lock()


def reset_json_mode_cache() -> None:
    """Yalnızca testler için — process-ömürlü cache'i temizler."""
    with _json_mode_lock:
        _json_mode_support.clear()


def create_chat_completion(client: OpenAI, *, model: str, json_mode: bool = False, base_url: str | None = None, **kwargs):
    """``client.chat.completions.create(model=model, **kwargs)`` — ``json_mode=True``
    ise önce ``response_format={"type": "json_object"}`` ekleyerek dener.

    Backend bu parametreyi reddederse (ör. yerel bir Jamba sunucusu
    ``response_format``'ı tanımıyorsa) ÇÖKMEZ: hatayı yakalar, bu
    ``(base_url, model)`` çifti için "desteklemiyor" olarak işaretler (bir
    sonraki çağrıda hiç denenmez, gereksiz round-trip'i tekrar ödemez) ve
    aynı isteği ``response_format`` OLMADAN tekrar dener. Çağıran taraf
    (router/multi_query/crag/post_hoc_verify) zaten geçersiz/olmayan JSON'a
    karşı kendi ayrıştırma fallback'ine sahip (bkz. her stage'in kendi
    ``_parse_*`` fonksiyonu) — bu fonksiyon yalnızca İSTEĞİN KENDİSİNİN
    reddedilmesini (400/‘bilinmeyen parametre’ gibi) ele alır, JSON
    ayrıştırma hatalarını değil."""
    key = (base_url or "", model)

    if json_mode:
        with _json_mode_lock:
            cached = _json_mode_support.get(key)

        if cached is not False:
            try:
                response = client.chat.completions.create(
                    model=model, response_format={"type": "json_object"}, **kwargs
                )
            except Exception as exc:
                logger.warning(
                    "Backend response_format (json_object) desteklemiyor gibi görünüyor "
                    "(model=%s, base_url=%s): %s — bu model için structured output kapatılıp "
                    "düz çağrıya düşülüyor (bir sonraki çağrıda tekrar denenmeyecek).",
                    model, base_url, exc,
                )
                with _json_mode_lock:
                    _json_mode_support[key] = False
            else:
                with _json_mode_lock:
                    _json_mode_support[key] = True
                return response

    return client.chat.completions.create(model=model, **kwargs)
