"""Resmî Gazete RSS connector — monitors new/amended legislation.

This uses the confirmed live RSS feed at resmigazete.gov.tr/rss (verified via
web search during design). Live connectivity from this development sandbox
could not be confirmed (network/TLS could not reach resmigazete.gov.tr — see
sample_data/legislation/README.md); verify this against the team's normal
dev environment before relying on it for scheduled ingestion runs.
"""
from __future__ import annotations

import feedparser

from mevzuat_rag.ingestion.base import SourceRef


class ResmiGazeteRSSConnector:
    def __init__(self, rss_url: str = "https://www.resmigazete.gov.tr/rss"):
        self.rss_url = rss_url

    def list_updates(self, since=None) -> list[SourceRef]:
        feed = feedparser.parse(self.rss_url)
        refs = []
        for entry in feed.entries:
            published = getattr(entry, "published_parsed", None)
            if since is not None and published is not None:
                from datetime import datetime

                entry_dt = datetime(*published[:6])
                if entry_dt < since:
                    continue
            refs.append(SourceRef(kanun_no="", kanun_adi=entry.get("title", ""), url=entry.get("link", "")))
        return refs
