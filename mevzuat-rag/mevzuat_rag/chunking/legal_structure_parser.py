"""Parses Turkish legislation text into a Madde/Fıkra/Bent tree.

Turkish mevzuat text follows a consistent structural convention:
  MADDE 5- (Başlık varsa parantez ya da büyük harfle)
  (1) Fıkra metni ...
      a) Bent metni ...
      b) Bent metni ...
  (2) Fıkra metni ...

This parser is regex-based, not ML-based: legislation formatting is
regular enough that a state machine is more reliable (and auditable) than a
model here, and citation accuracy matters more than recall on edge cases.
"""
from __future__ import annotations

import re

from mevzuat_rag.models import FikraNode, LegislationDocument, MaddeNode

MADDE_RE = re.compile(r"^\s*MADDE\s+(\d+)\s*[-–—]\s*(.*)$", re.IGNORECASE)
FIKRA_RE = re.compile(r"^\s*\((\d+)\)\s*(.*)$")
BENT_RE = re.compile(r"^\s*([a-zçğıöşü])\)\s*(.*)$", re.IGNORECASE)

# Resmi mevzuat kaynaklarının (mevzuat.gov.tr, Resmi Gazete) standart notasyonu:
# "MADDE 9- (Mülga: 12/7/2013-6495/77 md.)" ya da
# "MADDE 5- (Değişik: 10/6/2020-... md.) <yeni metin devam eder>"
# Not: sample_data/legislation/ içindeki 2 örnek belgede bu kalıbın gerçek bir
# örneği yok (corpus çok küçük/temiz) — testler bu yüzden sentetik metinlerle
# yazıldı, bkz. tests/test_durum_tracking.py.
DURUM_RE = re.compile(r"^\(?\s*(mülga|değişik)\b", re.IGNORECASE)

# Mevzuat hiyerarşisi çıkarımı: kanun_adi'deki anahtar kelimeye göre. Sıra
# önemli — "Kanun Hükmünde Kararname" başlığında "Kanun" kelimesi de geçer,
# bu yüzden khk deseni "kanun" varsayılanından ÖNCE kontrol edilir. Örnek:
# sample_data/legislation/2646_resmi_yazisma_yonetmeligi_madde5.md'nin
# KANUN_ADI'sı "... Hakkında Yönetmelik" — gerçek bir Yönetmelik, "Kanun"
# kelimesi hiç geçmiyor; bu heuristik onu doğru şekilde "yönetmelik" olarak
# sınıflandırır.
_MEVZUAT_TURU_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"anayasa", re.IGNORECASE), "anayasa"),
    (re.compile(r"kanun\s+hükmünde\s+kararname|\bkhk\b", re.IGNORECASE), "khk"),
    # "yönetmeli[kğ]": Türkçe ünsüz yumuşaması yüzünden "yönetmelik" kökü
    # ünlüyle başlayan ek aldığında k->ğ'ye döner ("yönetmeliği",
    # "yönetmeliğin" vb.) — yalnızca "yönetmelik" aransa bu çekimli halleri
    # kaçırırdı.
    (re.compile(r"yönetmeli[kğ]", re.IGNORECASE), "yönetmelik"),
    (re.compile(r"tebliğ", re.IGNORECASE), "tebliğ"),
]


def _infer_mevzuat_turu(kanun_adi: str) -> str:
    """kanun_adi başlığındaki anahtar kelimeye göre mevzuat türünü heuristik
    olarak çıkarır. Resmi bir sınıflandırma kaynağına bağlı değildir —
    corpus'taki başlık kalıplarına dayanan bir yaklaşıklamadır. Eşleşme
    yoksa (en yaygın durum) varsayılan "kanun" döner."""
    for pattern, turu in _MEVZUAT_TURU_PATTERNS:
        if pattern.search(kanun_adi):
            return turu
    return "kanun"


# Tablo/ek içeriği için MVP uyarı bayrağı — GERÇEK TABLO ÇIKARIMI YAPILMIYOR
# (kapsam dışı, çok zor). Yalnızca "bu satır muhtemelen bir tablo/ek satırı"
# şüphesini heuristik olarak işaretler; generation.py bunu LLM'e bir dikkat
# uyarısı olarak iletir. Sinyaller:
#   - markdown tarzı tablo çizgisi ("|")
#   - tab karakteri ya da 3+ ardışık boşlukla hizalanmış sütunlar
#   - art arda (aralarında yalnızca boşluk olan) sayı+birim grupları,
#     örn. "10 kg   5 adet" — tek bir "210x297 mm" gibi ölçü ifadesi bunu
#     TETİKLEMEZ, çünkü grup en az 2 kez ardışık tekrar etmeli.
# sample_data/legislation/ içindeki 2 gerçek belgede tablo örneği YOK (corpus
# küçük/temiz) — testler bu yüzden sentetik metinlerle yazıldı, dürüstçe not
# edilmiştir, bkz. tests/test_legal_hierarchy_and_tables.py.
_TABLE_PIPE_RE = re.compile(r"\|")
_TABLE_ALIGNED_COLUMNS_RE = re.compile(r"\S(?: {3,}|\t)\S")
_TABLE_NUMERIC_COLUMNS_RE = re.compile(
    r"(?:\d+[.,]?\d*\s*(?:kg|gr|g|lt|l|m2|m3|cm|mm|km|adet|tl|try|%|gün|ay|yıl)\b\s*){2,}",
    re.IGNORECASE,
)


def _looks_like_table_line(raw_line: str) -> bool:
    return bool(
        _TABLE_PIPE_RE.search(raw_line)
        or _TABLE_ALIGNED_COLUMNS_RE.search(raw_line)
        or _TABLE_NUMERIC_COLUMNS_RE.search(raw_line)
    )


def parse_legislation_text(raw_text: str, kanun_no: str, kanun_adi: str, kaynak_url: str) -> LegislationDocument:
    doc = LegislationDocument(
        kanun_no=kanun_no,
        kanun_adi=kanun_adi,
        kaynak_url=kaynak_url,
        mevzuat_turu=_infer_mevzuat_turu(kanun_adi),
    )
    current_madde: MaddeNode | None = None
    current_fikra: FikraNode | None = None
    current_bent_letter: str | None = None

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        madde_match = MADDE_RE.match(line)
        if madde_match:
            current_madde = MaddeNode(madde_no=int(madde_match.group(1)), baslik=None)
            doc.maddeler.append(current_madde)
            current_fikra = None
            current_bent_letter = None
            remainder = madde_match.group(2).strip()
            durum_match = DURUM_RE.match(remainder)
            if durum_match:
                current_madde.durum = durum_match.group(1).lower()
            if remainder:
                line = remainder
            else:
                continue

        if current_madde is None:
            # Preamble / non-madde text (başlık, dayanak vb.) — skip, not citable.
            continue

        if _looks_like_table_line(raw_line):
            current_madde.contains_table = True

        fikra_match = FIKRA_RE.match(line)
        if fikra_match:
            current_fikra = FikraNode(fikra_no=int(fikra_match.group(1)), bent=None, text="")
            current_madde.fikralar.append(current_fikra)
            current_bent_letter = None
            line = fikra_match.group(2).strip()
            if not line:
                continue

        if current_fikra is None:
            # Madde body with no explicit (1) marker — implicit first fıkra.
            current_fikra = FikraNode(fikra_no=1, bent=None, text="")
            current_madde.fikralar.append(current_fikra)

        bent_match = BENT_RE.match(line)
        if bent_match:
            current_bent_letter = bent_match.group(1).lower()
            bent_node = FikraNode(fikra_no=current_fikra.fikra_no, bent=current_bent_letter, text=bent_match.group(2).strip())
            current_madde.fikralar.append(bent_node)
            continue

        target = current_madde.fikralar[-1]
        target.text = (target.text + " " + line).strip() if target.text else line

    return doc
