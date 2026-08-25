"""mevzuat.gov.tr connector.

mevzuat.gov.tr (T.C. Cumhurbaşkanlığı Mevzuat Bilgi Sistemi) has no
documented public API. This implementation follows the search/fetch shape
used by the open-source ``saidsurucu/mevzuat-mcp`` project (search by
mevzuat adı/no, mevzuat türü, paginated; full text served as HTML per
mevzuat). It has NOT been verified against the live site from this sandbox
(TLS/network access to mevzuat.gov.tr was not reachable during development —
see ``docs/rag.md``), so treat the endpoint paths below as a documented
best-effort starting point, not a confirmed integration. Verify against the
live site (or vendor ``mevzuat-mcp`` directly, see its GitHub repo) before
relying on this for real ingestion runs.
"""
from __future__ import annotations

import httpx

from mevzuat_rag.ingestion.base import RawDocument, SourceRef
from mevzuat_rag.ingestion.normalize import html_to_text

SEARCH_URL = "https://www.mevzuat.gov.tr/anasayfa/MevzuatFihristDetayIframe"
BASE_URL = "https://www.mevzuat.gov.tr"

# Air-gapped kamu ortamı: canlı scraper devre dışı. Mevzuat metinleri
# sample_data/legislation/offline_docs/ altına elle eklenip
# mevzuat_rag.ingestion.local_corpus.load_offline_docs() ile indekslenir.
OFFLINE_MODE = True


class MevzuatGovTrConnector:
    def __init__(self, http_client: httpx.Client | None = None, rate_limit_s: float = 1.0):
        if OFFLINE_MODE:
            raise RuntimeError(
                "MevzuatGovTrConnector devre dışı (air-gapped mod). Mevzuatı "
                "sample_data/legislation/offline_docs/ altına ekleyip local_corpus "
                "üzerinden indeksleyin."
            )
        self.client = http_client or httpx.Client(timeout=20.0, follow_redirects=True)
        self.rate_limit_s = rate_limit_s

    def search(self, mevzuat_adi: str, mevzuat_turleri: list[str] | None = None, page: int = 1) -> list[SourceRef]:
        """Best-effort search — verify query params against the live site before use."""
        params = {"AranacakIfade": mevzuat_adi, "Sayfa": page}
        if mevzuat_turleri:
            params["MevzuatTur"] = ",".join(mevzuat_turleri)
        response = self.client.get(SEARCH_URL, params=params)
        response.raise_for_status()
        # NOTE: result-row parsing depends on the live page's DOM structure,
        # which was not verifiable from this environment. Placeholder no-op
        # until confirmed against the real site.
        return []

    def fetch(self, ref: SourceRef) -> RawDocument:
        response = self.client.get(ref.url)
        response.raise_for_status()
        return RawDocument(kanun_no=ref.kanun_no, kanun_adi=ref.kanun_adi, url=ref.url, raw_text=html_to_text(response.text))

    def list_updates(self, since=None) -> list[SourceRef]:
        return []
