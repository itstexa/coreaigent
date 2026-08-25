"""Loads the fixture legislation files under sample_data/legislation/.

Fixture format (see sample_data/legislation/README.md for provenance):
  KANUN_NO: <no>
  KANUN_ADI: <ad>
  KAYNAK_URL: <url>
  <blank line>
  MADDE 1- ...

Air-gapped/offline format (sample_data/legislation/offline_docs/): plain
``.txt`` dosyaları + yanlarında tek bir ``metadata.json`` (dosya adı -> kanun_no/
kanun_adi/mevzuat_turu/kaynak_url). Ağa hiç çıkmaz — bkz. load_offline_docs().
"""
from __future__ import annotations

import json
from pathlib import Path

from mevzuat_rag.ingestion.base import RawDocument
from mevzuat_rag.ingestion.normalize import normalize_whitespace

SAMPLE_DATA_DIR = Path(__file__).resolve().parents[2] / "sample_data" / "legislation"
OFFLINE_DOCS_DIR = SAMPLE_DATA_DIR / "offline_docs"


def _parse_fixture(path: Path) -> RawDocument:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = {}
    body_start = 0
    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i + 1
            break
        if ":" in line:
            key, _, value = line.partition(":")
            header[key.strip()] = value.strip()
    body = "\n".join(lines[body_start:])
    return RawDocument(
        kanun_no=header.get("KANUN_NO", path.stem),
        kanun_adi=header.get("KANUN_ADI", path.stem),
        url=header.get("KAYNAK_URL", ""),
        raw_text=body,
    )


def load_offline_docs(directory: Path = OFFLINE_DOCS_DIR) -> list[RawDocument]:
    """Air-gapped kaynak: <ad>.txt + metadata.json eşleşmesi, ağ erişimi yok.

    metadata.json biçimi: {"<dosya_adi>.txt": {"kanun_no", "kanun_adi",
    "mevzuat_turu"(opsiyonel), "kaynak_url"}}. metadata.json veya eşleşen
    kayıt yoksa o dosya sessizce atlanır (yarım/etiketlenmemiş dosya
    indekslenmez)."""
    metadata_path = directory / "metadata.json"
    if not metadata_path.exists():
        return []

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    docs = []
    for txt_path in sorted(directory.glob("*.txt")):
        entry = metadata.get(txt_path.name)
        if entry is None:
            continue
        raw_text = normalize_whitespace(txt_path.read_text(encoding="utf-8"))
        if not raw_text:
            continue
        docs.append(
            RawDocument(
                kanun_no=entry.get("kanun_no", txt_path.stem),
                kanun_adi=entry.get("kanun_adi", txt_path.stem),
                url=entry.get("kaynak_url", "yerel_veritabani"),
                raw_text=raw_text,
            )
        )
    return docs


def load_fixtures(directory: Path = SAMPLE_DATA_DIR) -> list[RawDocument]:
    fixtures = [_parse_fixture(p) for p in sorted(directory.glob("*.md")) if p.name.lower() != "readme.md"]
    fixtures.extend(load_offline_docs(directory / "offline_docs"))
    return fixtures
