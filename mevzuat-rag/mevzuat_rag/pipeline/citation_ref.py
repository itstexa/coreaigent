"""[9] Atıf tespiti — chunk metninde geçen madde-madde çapraz atıfları
regex ile bulur (legal_structure_parser.py'nin felsefesiyle aynı: "legislation
formatting is regular enough that a state machine/regex is more reliable and
auditable than a model here").

Kapsam: yalnızca AYNI KANUN İÇİ atıflar test edilmiştir — corpus'ta
doğrulanabilen tek gerçek örnek 3071 sayılı Kanun Madde 6.c'nin "4. maddede
gösterilen şartlar" ifadesiyle Madde 4'e atıfta bulunması. Kanunlar-arası
atıf ("2577 sayılı Kanun'un 7. maddesi") kalıbı yazılmadı — corpus'ta hiç
örneği yok, o yüzden test edilemeyen/kalibre edilemeyen bir regex eklemek
yanıltıcı olur (bkz. NOTES.md "Sonraki adımlar"). Külliyat genişleyip gerçek
kanunlar-arası atıf örnekleri gelince eklenmeli.
"""
from __future__ import annotations

import re

# Sırayla: "4. maddede" / "4. maddesi" / "4 üncü madde" / "5 inci maddesine"
# gibi kalıpları yakalar. "MADDE 6-" gibi madde BAŞLIKLARIYLA karışmaz çünkü
# başlıkta sayı "MADDE" kelimesinden SONRA gelir, burada ÖNCE gelmesi şart.
_MADDE_REF_RE = re.compile(
    r"\b(\d{1,3})\s*\.?\s*(?:inci|nci|ncı|ncu|üncü|uncu)?\s*madde(?:sinde|sine|since|sinin|si|de|ye|nin)?\b",
    re.IGNORECASE,
)


def extract_same_kanun_refs(text: str, own_madde_no: int | None) -> set[int]:
    """Metinde geçen madde numaralarını döndürür — kendi madde numarasını
    (kendine atıf, çapraz atıf sayılmaz) ve büyük ihtimalle yanlış-pozitif
    olan tek haneli küçük sayıları (ör. "3 kişi") elemeye çalışmaz; regex
    zaten "madde" kelimesine bitişik sayı arıyor, o yüzden bu risk düşük."""
    refs = {int(m.group(1)) for m in _MADDE_REF_RE.finditer(text)}
    refs.discard(own_madde_no)
    return refs
