"""Normalization rules for Turkish legislation text before embedding/BM25.

WHY: Qdrant stores embedding vectors tied to exact chunk text. Any rule change
must bump TEXT_NORM_VERSION so store metadata fails fast instead of mixing
incompatible vectors.
"""
from __future__ import annotations

import re
import unicodedata

TEXT_NORM_VERSION: str = "1.0.0"

_VALID_PROFILES = {"embedding", "lexical", "display"}

_SOFT_HYPHEN = "­"
_ZERO_WIDTH_SPACE = "​"
_NON_BREAKING_SPACE = " "

_WHITESPACE_RE = re.compile(r" +")
_NEWLINE_RE = re.compile(r"\n{3,}")
_DEHYPHENATION_RE = re.compile(r"(?<=[A-Za-zÇĞİÖŞÜçğıöşü])-\s*\n\s*(?=[A-Za-zÇĞİÖŞÜçğıöşü])")

_QUOTE_TRANSLATION = str.maketrans({
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "«": '"',
    "»": '"',
})

_TURKISH_LOWER_MAP = str.maketrans({"I": "ı", "İ": "i"})
_TURKISH_UPPER_MAP = str.maketrans({"i": "İ", "ı": "I"})
_ASCII_FOLD_MAP = str.maketrans({
    "ç": "c", "Ç": "c",
    "ğ": "g", "Ğ": "g",
    "ı": "i", "I": "i",
    "i": "i", "İ": "i",
    "ö": "o", "Ö": "o",
    "ş": "s", "Ş": "s",
    "ü": "u", "Ü": "u",
})


def _normalize_unicode(text: str) -> str:
    """NFC normalize eder ki compose/decompose formları ayrılmasın."""
    return unicodedata.normalize("NFC", text)


def _strip_invisible_chars(text: str) -> str:
    """Görünmez karakterleri kaldırır, NBSP'yi normal boşluğa çevirir."""
    return (
        text.replace(_SOFT_HYPHEN, "")
        .replace(_ZERO_WIDTH_SPACE, "")
        .replace(_NON_BREAKING_SPACE, " ")
    )


def _normalize_quotes(text: str) -> str:
    """Eğik tırnakları düz forma indirger."""
    return text.translate(_QUOTE_TRANSLATION)


def _dehyphenate(text: str) -> str:
    """Satır sonu heceleme tiresini birleştirir; numeral tireleri korur."""
    return _DEHYPHENATION_RE.sub("", text)


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _turkish_lower(text: str) -> str:
    """Türkçe-farkında lowercase üretir."""
    return text.translate(_TURKISH_LOWER_MAP).lower()


def _turkish_upper(text: str) -> str:
    """Türkçe-farkında uppercase üretir."""
    return text.translate(_TURKISH_UPPER_MAP).upper()


def _ascii_fold(text: str) -> str:
    """Türkçe karakterleri ASCII karşılıklarına indirger."""
    return text.translate(_ASCII_FOLD_MAP)


def normalize_text(text: str, *, profile: str = "embedding") -> str:
    """Tek giriş noktası: profile göre normalizasyon uygular."""
    if profile not in _VALID_PROFILES:
        raise ValueError(f"Bilinmeyen normalizasyon profili: {profile}")

    if profile == "display":
        return _normalize_whitespace(_strip_invisible_chars(_normalize_unicode(text)))

    normalized = _normalize_whitespace(
        _dehyphenate(_normalize_quotes(_strip_invisible_chars(_normalize_unicode(text))))
    )

    if profile == "lexical":
        return _ascii_fold(_turkish_lower(normalized))

    return normalized
