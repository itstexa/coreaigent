"""Small, deterministic redactor for the approved BX-01 export slice."""

from __future__ import annotations

import re
from collections import Counter


class DlpError(ValueError):
    """The source cannot be safely projected into the training export."""


TCKN_PATTERN = re.compile(r"(?<!\d)\d{11}(?!\d)")
NAME_LABEL_PATTERN = re.compile(
    r"(?im)^(?:ad\s*soyad(?:ı)?|başvuru\s*sahibi|isim)\s*:\s*(?P<value>[^\r\n]+)$"
)


def _span(spans: list[tuple[int, int, str]], start: int, end: int, field: str) -> None:
    if start >= end:
        raise DlpError("empty DLP span")
    for other_start, other_end, other_field in spans:
        if (start, end, field) == (other_start, other_end, other_field):
            return
        if start < other_end and end > other_start:
            raise DlpError("overlapping DLP spans")
    spans.append((start, end, field))


def redact_text(text: str, names=()) -> dict:
    """Replace approved PII classes and return only redacted projection data.

    ``names`` comes from current validation fields, allowing each document's
    detected name value to be marked without a fixed person-name dictionary.
    A supplied value that cannot be located fails closed.
    """
    if not isinstance(text, str):
        raise DlpError("source text must be a string")
    spans: list[tuple[int, int, str]] = []
    for match in TCKN_PATTERN.finditer(text):
        _span(spans, match.start(), match.end(), "tckn")
    for match in NAME_LABEL_PATTERN.finditer(text):
        _span(spans, match.start("value"), match.end("value"), "name")
    for name in names or ():
        if not isinstance(name, str) or not name.strip():
            raise DlpError("name value is invalid")
        matches = list(re.finditer(re.escape(name), text, re.IGNORECASE))
        if not matches:
            raise DlpError("name value was not found in source text")
        for match in matches:
            _span(spans, match.start(), match.end(), "name")
    spans.sort(key=lambda item: item[0])
    placeholders = {"name": "<ANON_NAME>", "tckn": "<ANON_TCKN>"}
    redacted = text
    counts: Counter[str] = Counter()
    for start, end, field in reversed(spans):
        redacted = redacted[:start] + placeholders[field] + redacted[end:]
        counts[field] += 1
    return {
        "text": redacted,
        "redactions": [
            {"field": field, "placeholder": placeholders[field], "count": counts[field]}
            for field in ("name", "tckn") if counts[field]
        ],
    }
