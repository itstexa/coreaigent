"""Deterministic rules used by the Rule Engine baseline.

Scores returned here are heuristic coverage scores in the 0..1 range.  They
are deliberately not probabilities and must not be treated as confidence.
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

EVRAK_TURU_KURALLAR: dict[str, dict[str, object]] = {
    "dilekçe": {"anahtar_kelimeler": ["talep", "başvuru", "istemek", "gereğini arz ederim", "lütfen", "imkan", "destek", "yardım", "değişiklik", "belgesini gönder", "yapılmasını talep"], "zorunlu_alanlar_tipi": "temel"},
    "şikayet": {"anahtar_kelimeler": ["şikayet", "problem", "sorun", "hata", "yanlış", "uygunsuz", "tehlike", "eksik", "arıza", "ince", "denetim", "inceleme", "rahatsız", "mağdur", "zararıma"], "zorunlu_alanlar_tipi": "kapsamli"},
    "bilgi_talebi": {"anahtar_kelimeler": ["bilgi", "öğrenme", "sorgulama", "koşul", "prosedür", "nasıl", "ne zaman", "nerede", "kaç", "hangi", "durum", "haber", "ayrıntı", "durumum", "açıklamasını istiyorum"], "zorunlu_alanlar_tipi": "minimal"},
    "başvuru_formu": {"anahtar_kelimeler": ["başvuru", "başvurmak", "katılım", "kaydolma", "kayıt", "başvurmakla", "değerlendirmesi", "programa katılma"], "zorunlu_alanlar_tipi": "kapsamli"},
    "itiraz": {"anahtar_kelimeler": ["itiraz", "haksız", "yanlış", "yeniden inceleme", "iptali", "kaldırması", "düzeltilmesi", "iptal", "karşı çıkıyorum", "karşılaştırması"], "zorunlu_alanlar_tipi": "kapsamli"},
}

KONU_BIRIM_ESLESME: dict[str, dict[str, object]] = {
    "fen_isleri": {"birim": "Fen İşleri Müdürlüğü", "anahtar_kelimeler": ["yol", "kaldırım", "sokak", "köprü", "asfalt", "çukur", "pothole", "altyapı", "kanalizasyon", "elektrik hattı", "ağaç", "temizlik", "fen", "bakım onarım"]},
    "imar": {"birim": "İmar ve Şehircilik Müdürlüğü", "anahtar_kelimeler": ["imar", "ruhsat", "yapı", "taş", "parsel", "ada", "kaçak yapı", "yıkım", "inşaat", "bina", "konut"]},
    "mali": {"birim": "Mali Hizmetler Müdürlüğü", "anahtar_kelimeler": ["vergi", "fatura", "borç", "su", "elektrik", "doğalgaz", "gaz", "mali", "makbuz", "ödeme", "kesinti", "ceza"]},
    "ik": {"birim": "İnsan Kaynakları Müdürlüğü", "anahtar_kelimeler": ["personel", "maaş", "izin", "başvuru", "sicil", "görev", "çalışan", "istihdam", "emekli", "yer değişikliği", "bordro"]},
    "sosyal": {"birim": "Sosyal Hizmetler Müdürlüğü", "anahtar_kelimeler": ["sosyal yardım", "yaşlı", "engelli", "zor durum", "yardım", "bakıcı", "bakım", "destek", "muhtaç", "ihtiyaçlı"]},
    "saglik": {"birim": "Sağlık Hizmetleri Müdürlüğü", "anahtar_kelimeler": ["hastane", "sağlık", "aşı", "tıbbi", "doktor", "randevu", "tedavi", "sağlık hizmeti"]},
    "zabita": {"birim": "Zabıta Müdürlüğü", "anahtar_kelimeler": ["gürültü", "trafik", "emniyet", "kabahat", "ceza", "tutanak", "güvenlik", "polis", "şikayet", "düzen"]},
    "egitim": {"birim": "Eğitim Müdürlüğü", "anahtar_kelimeler": ["okul", "öğrenci", "not", "eğitim", "öğretmen", "sınav", "burs", "sınıf", "akademik", "derece"]},
    "cevre": {"birim": "Çevre Müdürlüğü", "anahtar_kelimeler": ["çevre", "kirliliği", "atık", "duman", "koku", "kirli", "zehirli", "hava", "ağaç", "yeşil"]},
    "kultur": {"birim": "Kültür ve Turizm Müdürlüğü", "anahtar_kelimeler": ["kültür", "sergi", "kütüphane", "kitap", "sanat", "etkinlik", "turizm", "turist", "tarihî"]},
    "tarim": {"birim": "Tarım Müdürlüğü", "anahtar_kelimeler": ["tarım", "hayvan", "ürün", "çiftçi", "arazi", "mahsul", "zirai", "destekmiş", "tarımsal"]},
}

ZORUNLU_ALANLAR_TABLOSU: dict[str, list[str]] = {
    "dilekçe_temel": ["Ad Soyad", "Adres", "Telefon"],
    "şikayet_kapsamli": ["Ad Soyad", "Adres", "Telefon", "Şikayet Konusu"],
    "başvuru_formu_kapsamli": ["Ad Soyad", "TC Kimlik No", "Adres", "Telefon", "E-posta", "İlişkili Belgeler"],
    "itiraz_kapsamli": ["Ad Soyad", "Karar/Tutanak No", "Tebliğ Tarihi", "İtiraz Gerekçesi", "İspat Belgeleri"],
    "bilgi_talebi_minimal": ["Ad Soyad", "TC Kimlik No", "Telefon"],
}

KONU_MEVZUAT_ESLESTIRMESI: dict[str, list[str]] = {
    "sosyal yardım": ["5434 Sayılı Sosyal Yardımlaşma ve Dayanışmayı Teşvik Kanunu", "Ailenin Korunması ve Çocuk Hakları Kanunu"],
    "engelli": ["Engelliler Kanunu", "Engelli ve Yaşlı Bakım Kurumları Yönetmeliği"],
    "istihdam": ["İş Kanunu", "Memurlar Kanunu"], "eğitim": ["Milli Eğitim Kanunu", "Öğretmen Devlet Memurluğu Kanunu"],
    "sağlık": ["Sağlık Hizmetleri Sunumu Yönetmeliği", "Hasta Hakları Yönetmeliği"],
    "çevre": ["Çevre Kanunu", "Hava Kirliliği Kontrol Yönetmeliği"], "trafik": ["Kabahatler Kanunu", "Karayolları Trafik Yönetmeliği"],
    "vergi": ["Vergi Usul Kanunu", "Mali İşler Yönetmeliği"], "imar": ["Yapı Denetim Sistemi Kanunu", "Tapu Kanunu"],
}

YAZI_TURU_ESLESTIRMESI = {
    ("dilekçe", "İnsan Kaynakları Müdürlüğü"): ["Başvuru Sonuç Yazısı", "Başvuru Kabul Yazısı"],
    ("şikayet", "Zabıta Müdürlüğü"): ["Soruşturma Başlatma Yazısı", "Müfettiş Görevlendir Yazısı"],
    ("bilgi_talebi", "*"): ["Bilgi Yanıt Yazısı", "Bilgilendirme Metni"],
    ("başvuru_formu", "Sosyal Hizmetler Müdürlüğü"): ["Başvuru Kabul Yazısı", "Başvuru Red Yazısı"],
    ("itiraz", "*"): ["İtiraz Sonuç Yazısı", "Yeniden İnceleme Yazısı"],
}

_FIELD_PATTERNS = {
    "Ad Soyad": r"(?im)(?:ad[ıi]m?|ad soyad)\s*[:\-]?\s*[A-ZÇĞİÖŞÜ][a-zçğıöşü]+\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+",
    "TC Kimlik No": r"\b\d{11}\b", "Telefon": r"\b0\d{3}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b",
    "E-posta": r"[\w.+-]+@[\w-]+\.[\w.-]+", "Adres": r"(?i)\b(mahalle|mah\.?|sokak|sk\.?|cadde|cd\.?|köy|adres)\b",
    "Karar/Tutanak No": r"(?i)\b(karar|tutanak)\s*(no)?\s*[:\-]?\s*\w+", "Tebliğ Tarihi": r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b",
    "İtiraz Gerekçesi": r"(?i)\b(gerekçe|haksız|yanlış|itiraz)\b", "İspat Belgeleri": r"(?i)\b(ek|belge|kanıt|ispat)\b",
    "İlişkili Belgeler": r"(?i)\b(ek|belge|dosya)\b", "Şikayet Konusu": r"(?i)\b(şikayet|sorun|problem|uygunsuz|arıza)\b",
}

def _coverage(text: str, keywords: Sequence[str]) -> float:
    matches = sum(keyword.lower() in text.lower() for keyword in keywords)
    return round(matches / len(keywords), 2) if keywords else 0.0

def score_document_type(text: str) -> tuple[str, float]:
    """Return the best type and its keyword-coverage heuristic score."""
    if not text.strip(): return "dilekçe", 0.0
    scores = {name: _coverage(text, cfg["anahtar_kelimeler"]) for name, cfg in EVRAK_TURU_KURALLAR.items()}
    if text.lstrip().lower().startswith("sayın"): scores["dilekçe"] = min(1.0, scores["dilekçe"] + 0.1)
    for name in ("şikayet", "itiraz"):
        if name in text.lower()[:50]: scores[name] = min(1.0, scores[name] + 0.15)
    best = max(scores, key=scores.get)
    return (best if scores[best] else "dilekçe"), scores[best]

def find_department(text: str) -> tuple[str, float]:
    """Return department and independent keyword-coverage heuristic score."""
    scores = {str(rule["birim"]): _coverage(text, rule["anahtar_kelimeler"]) for rule in KONU_BIRIM_ESLESME.values()}
    best = max(scores, key=scores.get)
    return (best, scores[best]) if scores[best] else ("Genel Sekreterlik", 0.0)

def check_missing_fields(text: str, doc_type: str, required_table: Mapping[str, Sequence[str]] = ZORUNLU_ALANLAR_TABLOSU) -> list[str]:
    field_group = f"{doc_type}_{EVRAK_TURU_KURALLAR[doc_type]['zorunlu_alanlar_tipi']}"
    return [field for field in required_table.get(field_group, []) if not re.search(_FIELD_PATTERNS[field], text)]

def suggest_legislation(text: str) -> list[str]:
    for subject, laws in KONU_MEVZUAT_ESLESTIRMESI.items():
        if subject in text.lower(): return laws[:2]
    return ["Genel Kamu Yönetimi Kanunu"]

def select_draft_type(doc_type: str, department: str) -> str:
    return YAZI_TURU_ESLESTIRMESI.get((doc_type, department), YAZI_TURU_ESLESTIRMESI.get((doc_type, "*"), ["Resmi Yazı"]))[0]
