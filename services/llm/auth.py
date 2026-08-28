"""[Güvenlik] API-key tabanlı erişim kontrolü — services/workflow/auth.py ile
aynı desen, ayrı env değişkeni (LLM_API_KEYS) ile bağımsız yönetilir çünkü
compose.yaml'da llm ayrı bir container/servis olarak deploy ediliyor.

Bkz. services/workflow/auth.py docstring'i — JWT/session yerine API-key
seçilme gerekçesi ve WORKFLOW_API_KEYS boşken auth'un devre dışı kalması
sınırlaması burada da aynen geçerli.
"""
from __future__ import annotations

import os

from fastapi import Header, HTTPException


def _load_api_keys() -> dict[str, str]:
    raw = os.environ.get("LLM_API_KEYS", "")
    keys: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        key, _, actor = pair.partition(":")
        key, actor = key.strip(), actor.strip()
        if key and actor:
            keys[key] = actor
    return keys


async def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> str:
    api_keys = _load_api_keys()
    if not api_keys:
        return "anonymous"
    if not x_api_key or x_api_key not in api_keys:
        raise HTTPException(status_code=401, detail="Geçersiz veya eksik X-API-Key")
    return api_keys[x_api_key]
