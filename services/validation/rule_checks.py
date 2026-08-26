import re

DATE_NUMERIC_PATTERN = re.compile(
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
    re.IGNORECASE
)

DATE_TURKISH_MONTH_PATTERN = re.compile(
    r"\b\d{1,2}\s+(ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)\s+\d{2,4}\b",
    re.IGNORECASE
)

PHONE_PATTERN = re.compile(
    r"\b0?\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b",
    re.IGNORECASE
)

EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE
)

ADDRESS_KEYWORD_PATTERN = re.compile(
    r"\badres\b",
    re.IGNORECASE
)

REFERENCE_NUMBER_PATTERN = re.compile(
    r"\b(sayı|no:|referans)\s*[:]?\s*\d+\b",
    re.IGNORECASE
)

INVOICE_NUMBER_PATTERN = re.compile(
    r"\b(fatura\s*no|fatura\s*numarası)\s*[:]?\s*\d+\b",
    re.IGNORECASE
)

AMOUNT_PATTERN = re.compile(
    r"(?:₺|tl|tutar)\s*[:]?\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?",
    re.IGNORECASE
)


def regex_field_present(field_name: str, text: str) -> bool:
    if field_name == "tarih":
        return bool(DATE_NUMERIC_PATTERN.search(text) or DATE_TURKISH_MONTH_PATTERN.search(text))
    elif field_name == "iletişim bilgisi":
        return bool(PHONE_PATTERN.search(text) or EMAIL_PATTERN.search(text) or ADDRESS_KEYWORD_PATTERN.search(text))
    elif field_name == "referans sayı":
        return bool(REFERENCE_NUMBER_PATTERN.search(text))
    elif field_name == "fatura no":
        return bool(INVOICE_NUMBER_PATTERN.search(text))
    elif field_name == "tutar":
        return bool(AMOUNT_PATTERN.search(text))
    else:
        return False
