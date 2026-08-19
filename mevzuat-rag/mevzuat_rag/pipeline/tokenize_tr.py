"""Lightweight Turkish tokenizer for BM25 — correct Turkish case folding
(İ/I aren't ASCII-safe: "İstanbul".lower() != "istanbul" in the C locale),
punctuation stripping, a small legal/general stopword list, and Snowball
Turkish stemming. Not a full NLP pipeline — good enough for BM25 term
matching, which is the only thing that consumes it.
"""
from __future__ import annotations

import re

import snowballstemmer

_stemmer = snowballstemmer.stemmer("turkish")
_TOKEN_RE = re.compile(r"[a-zçğıöşü0-9]+")

_STOPWORDS = frozenset(
    {
        "acaba", "ama", "aslında", "az", "bazı", "belki", "biri", "birkaç", "birşey", "biz", "bu",
        "çok", "çünkü", "da", "daha", "de", "defa", "diye", "eğer", "en", "gibi", "hem", "hepsi",
        "her", "hiç", "için", "ile", "ise", "kez", "ki", "kim", "mı", "mu", "mü", "nasıl", "ne",
        "neden", "nerde", "nerede", "nereye", "niçin", "niye", "o", "sanki", "şey", "siz", "şu",
        "tüm", "ve", "veya", "ya", "yani",
    }
)


def _turkish_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def tokenize(text: str) -> list[str]:
    lowered = _turkish_lower(text)
    raw_tokens = _TOKEN_RE.findall(lowered)
    tokens = [t for t in raw_tokens if t not in _STOPWORDS and len(t) > 1]
    return _stemmer.stemWords(tokens)
