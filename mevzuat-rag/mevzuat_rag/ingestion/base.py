"""Common interface every ingestion backend implements.

Chunking/embedding/indexing code only ever talks to this interface — it
never knows whether a document came from mevzuat.gov.tr, Resmi Gazete RSS,
a generic web fetch, or a local fixture file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SourceRef:
    kanun_no: str
    kanun_adi: str
    url: str


@dataclass
class RawDocument:
    kanun_no: str
    kanun_adi: str
    url: str
    raw_text: str


class IngestionConnector(Protocol):
    def fetch(self, ref: SourceRef) -> RawDocument: ...

    def list_updates(self, since=None) -> list[SourceRef]: ...
