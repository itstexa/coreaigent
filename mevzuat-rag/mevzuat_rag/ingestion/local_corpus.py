"""Loads the fixture legislation files under sample_data/legislation/.

Fixture format (see sample_data/legislation/README.md for provenance):
  KANUN_NO: <no>
  KANUN_ADI: <ad>
  KAYNAK_URL: <url>
  <blank line>
  MADDE 1- ...
"""
from __future__ import annotations

from pathlib import Path

from mevzuat_rag.ingestion.base import RawDocument

SAMPLE_DATA_DIR = Path(__file__).resolve().parents[2] / "sample_data" / "legislation"


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


def load_fixtures(directory: Path = SAMPLE_DATA_DIR) -> list[RawDocument]:
    return [_parse_fixture(p) for p in sorted(directory.glob("*.md")) if p.name.lower() != "readme.md"]
