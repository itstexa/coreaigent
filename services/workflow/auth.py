"""[Güvenlik] API-key tabanlı erişim kontrolü.

Bu servis (workflow orchestrator), pipeline.py üzerinden mevzuat-rag'ın
indekslediği kamu evrakı içeriğine erişiyor. Denetimde bulunan boşluk:
"herhangi bir çağıran her içeriği sorgulayabilir, kim sorduğu hiç
loglanmıyor" — services/workflow/main.py'nin /upload, /v1/workflows/document,
/status/{id}, /result/{id} uçları hiçbir auth kontrolü olmadan tüm ağdan
erişilebilirdi (main.py'de Depends yoktu, repo genelinde jwt/authorization/
api-key deseni sıfır sonuç veriyordu).

JWT/session değil API-key seçildi: sistemde henüz bir login/kullanıcı
deposu akışı yok (static/ altındaki tek sayfa oturum kavramı içermiyor) —
JWT bir login endpoint'i, session bir kullanıcı deposu ister; ikisi de şu an
var olmayan altyapı gerektirir. API-key, önceden paylaşılan kimlik
gerektiren servis-to-servis / operatör erişimi için asgari yeterli kontroldür.

Format: WORKFLOW_API_KEYS="anahtar1:aktor_adi1,anahtar2:aktor_adi2"

BİLİNÇLİ SINIRLAMA: WORKFLOW_API_KEYS tanımsız/boşsa (dev/test/mock ortamı,
ör. compose.yaml'daki contract-mock stack) auth devre dışı kalır ve
actor="anonymous" döner — mevcut testleri/mock akışını kırmamak için. Bu,
PRODUCTION'da bu değişken unutulursa erişim kontrolünün SESSİZCE devre dışı
kalacağı anlamına gelir; deploy checklist'ine bu değişkenin varlığını
doğrulayan bir adım eklenmelidir (bkz. rag_config_panel.py, madde 1 notu).
"""
from __future__ import annotations

import os

from fastapi import Header, HTTPException


def _load_api_keys() -> dict[str, str]:
    raw = os.environ.get("WORKFLOW_API_KEYS", "")
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
    """FastAPI dependency: geçerli anahtar varsa actor adını döner, yoksa 401."""
    api_keys = _load_api_keys()
    if not api_keys:
        return "anonymous"
    if not x_api_key or x_api_key not in api_keys:
        raise HTTPException(status_code=401, detail="Geçersiz veya eksik X-API-Key")
    return api_keys[x_api_key]
