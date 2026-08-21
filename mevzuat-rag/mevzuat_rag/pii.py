"""[7] PII Redaksiyon — kimlik/iletişim bilgilerini LLM'e/vektör deposuna
ulaşmadan önce maskeler.

Bu modül regex + doğrulama tabanlıdır (NER değil): TC Kimlik No için resmi
checksum algoritması kullanılır (yalnızca 11 haneli sayı olması yetmez,
gerçek bir TCKN gibi doğrulanması gerekir) — aksi halde madde/kanun/dosya
numaraları gibi rastgele 11 haneli sayılar da yanlışlıkla maskelenir.

Kapsam dışı (regex'in yapamayacağı): serbest metindeki isim/soyisim ve açık
adres tespiti — bunlar NER gerektirir. Bu modül yalnızca yapısal/örüntüsü
belirgin alanları (TCKN, telefon, e-posta, IBAN) yakalar; NER katmanı ayrı
bir sonraki adım olarak NOTES.md'ye eklenmiştir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TCKN_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+90[ .-]?|0)?5\d{2}[ .-]?\d{3}[ .-]?\d{2}[ .-]?\d{2}(?!\d)"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IBAN_RE = re.compile(r"(?<![A-Z0-9])TR\d{2}(?:[ ]?\d{4}){5}[ ]?\d{2}(?![0-9])")

_TAGS = {
    "tckn": "[TCKN]",
    "telefon": "[TELEFON]",
    "eposta": "[EPOSTA]",
    "iban": "[IBAN]",
}


def _tckn_checksum_valid(digits: str) -> bool:
    """Resmi TCKN algoritması (bkz. Nüfus ve Vatandaşlık İşleri Genel Müdürlüğü
    formülü): 11. hane rastgele değildir, ilk 10 haneden hesaplanır."""
    if digits[0] == "0":
        return False
    d = [int(c) for c in digits]
    odd_sum = d[0] + d[2] + d[4] + d[6] + d[8]
    even_sum = d[1] + d[3] + d[5] + d[7]
    check10 = ((odd_sum * 7) - even_sum) % 10
    if check10 != d[9]:
        return False
    check11 = sum(d[:10]) % 10
    return check11 == d[10]


@dataclass
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact_pii(text: str) -> RedactionResult:
    """Sırasıyla IBAN, e-posta, telefon, TCKN — bu sıra önemli: IBAN/e-posta
    kendi ayırt edici karakterlerine (harf, @) sahip olduğu için önce
    ayıklanırsa, geriye kalan saf rakam dizilerinde TCKN/telefon araması
    daha az yanlış pozitif üretir."""
    counts = {k: 0 for k in _TAGS}

    def _sub_count(pattern: re.Pattern, key: str, s: str) -> str:
        def _repl(_m: re.Match) -> str:
            counts[key] += 1
            return _TAGS[key]

        return pattern.sub(_repl, s)

    out = text
    out = _sub_count(_IBAN_RE, "iban", out)
    out = _sub_count(_EMAIL_RE, "eposta", out)
    out = _sub_count(_PHONE_RE, "telefon", out)

    def _tckn_repl(m: re.Match) -> str:
        candidate = m.group(0)
        if _tckn_checksum_valid(candidate):
            counts["tckn"] += 1
            return _TAGS["tckn"]
        return candidate

    out = _TCKN_RE.sub(_tckn_repl, out)

    return RedactionResult(text=out, counts={k: v for k, v in counts.items() if v})
