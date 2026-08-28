"""Bounded Turkish writing suggestions; never rewrites protected spans."""
import re

PROTECTED = re.compile(r"\b(?:\d{11}|\d+[.,]\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü]+)*)\b")

def suggest(text, language="tr"):
    if language not in {"tr", "tur"}:
        return {"status": "unsupported_language", "original_text": text, "suggested_text": None, "changed": False}
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text is required")
    spans = []
    def hold(match):
        spans.append(match.group(0)); return f"\x00{len(spans)-1}\x00"
    masked = PROTECTED.sub(hold, text)
    normalized = re.sub(r"[ \t]+", " ", masked.strip())
    normalized = re.sub(r"\s+([,.;:!?])", r"\1", normalized)
    normalized = re.sub(r"([.!?])(?=[A-Za-zÇĞİÖŞÜçğıöşü])", r"\1 ", normalized)
    normalized = normalized[:1].upper() + normalized[1:] if normalized else normalized
    for index, value in enumerate(spans): normalized = normalized.replace(f"\x00{index}\x00", value)
    return {"status": "ok", "original_text": text, "suggested_text": normalized, "changed": normalized != text}
