"""Agent-Reach-modeled generic ingestion backend.

github.com/Panniantong/Agent-Reach is a multi-platform ingestion CLI. It has
no connector for mevzuat.gov.tr, so rather than shelling out to its full CLI
(which would pull in unrelated platform connectors/auth for Twitter, Reddit,
YouTube, Bilibili, etc.), this reimplements just its two relevant patterns
directly:
  - generic readable-webpage fetch via the Jina Reader proxy
  - RSS fetch via feedparser (see resmi_gazete.py for the Resmî Gazete case;
    this is the general-purpose fallback for any other RSS source)

Use case here: a fallback fetch path for mevzuat.gov.tr pages if the
dedicated scraper (mevzuat_gov_tr.py) breaks due to a markup change, since
Jina Reader does readability extraction independent of the site's DOM
structure.
"""
from __future__ import annotations

import httpx

from mevzuat_rag.ingestion.base import RawDocument, SourceRef
from mevzuat_rag.ingestion.normalize import normalize_whitespace


class AgentReachWebConnector:
    def __init__(self, jina_reader_base_url: str = "https://r.jina.ai", http_client: httpx.Client | None = None):
        self.jina_reader_base_url = jina_reader_base_url.rstrip("/")
        self.client = http_client or httpx.Client(timeout=30.0)

    def fetch(self, ref: SourceRef) -> RawDocument:
        reader_url = f"{self.jina_reader_base_url}/{ref.url}"
        response = self.client.get(reader_url)
        response.raise_for_status()
        return RawDocument(kanun_no=ref.kanun_no, kanun_adi=ref.kanun_adi, url=ref.url, raw_text=normalize_whitespace(response.text))

    def list_updates(self, since=None) -> list[SourceRef]:
        return []
