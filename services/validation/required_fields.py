from typing import Dict, List, Tuple

REQUIRED_FIELDS: Dict[str, List[Tuple[str, str]]] = {
    "petition": [("iletişim bilgisi", "regex"), ("tarih", "regex"), ("talep konusu", "llm")],
    "application": [("ad soyad", "llm"), ("tarih", "regex")],
    "complaint": [("şikayet konusu", "llm"), ("tarih", "regex")],
    "information_request": [("talep edilen bilgi", "llm"), ("gerekçe", "llm")],
    "official_letter": [("muhatap kurum", "llm"), ("konu", "llm"), ("referans sayı", "regex")],
    "invoice": [("fatura no", "regex"), ("tutar", "regex"), ("tarih", "regex")],
    "unsupported": [],
}
