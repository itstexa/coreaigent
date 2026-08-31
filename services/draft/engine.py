"""Deterministic official-letter draft generator for public documents."""
from __future__ import annotations

from typing import Iterable, List

VALID_LETTER_TYPES = (
    "cevap",
    "üst_yazı",
    "bilgilendirme",
    "eksik_bilgi_talebi",
    "yönlendirme",
)


class DraftError(ValueError):
    """Raised when the request payload is not valid for draft generation."""


def _as_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise DraftError(f"{field_name} must be a string")
    text = value.strip()
    if not text:
        raise DraftError(f"{field_name} must not be empty")
    return text


def _as_list(value: object, field_name: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        cleaned = []
        for item in value:
            if not isinstance(item, str):
                raise DraftError(f"{field_name} must contain only strings")
            text = item.strip()
            if text:
                cleaned.append(text)
        return cleaned
    raise DraftError(f"{field_name} must be a list of strings or a string")


def _normalize_subject(summary: str, document: str) -> str:
    subject = summary.strip() or document.strip()
    if len(subject) > 120:
        subject = subject[:117].rstrip() + "..."
    return subject


def infer_letter_type(summary: str, missing_info: Iterable[str], routing: str) -> str:
    text = f"{summary} {routing}".lower()
    missing = list(missing_info)
    if missing:
        return "eksik_bilgi_talebi"
    if "yönlendir" in text or "yönlendirme" in text:
        return "yönlendirme"
    if "bilgilendirme" in text or "duyuru" in text or "bilgi" in text and "güncelleme" in text:
        return "bilgilendirme"
    if "üst yazı" in text or "üst yazi" in text or "kurum" in text and "gönder" in text:
        return "üst_yazı"
    return "cevap"


def render_draft(letter_type: str, subject: str, routing: str, document: str, missing_info: List[str]) -> str:
    route_name = routing.strip() or "Yetkili Birim"
    if letter_type == "eksik_bilgi_talebi":
        required = ", ".join(missing_info) if missing_info else "ilgili evrak için gerekli detaylar"
        return (
            f"Sayın {route_name},\n\n"
            f"{subject} konulu başvuruda işlem için eksik bilgi bulunmaktadır. "
            f"Aşağıdaki hususların gönderilmesi gerekmektedir: {required}.\n\n"
            "İlave bilgi iletilmesi halinde işleme devam edilecektir.\n\n"
            "Saygılarımla,"
        )
    if letter_type == "yönlendirme":
        return (
            f"Sayın {route_name},\n\n"
            f"{subject} konulu dosya, ilgili iş akışı kapsamında tarafınıza yönlendirilmiştir. "
            "İşlem ve gerekli takip için ilgili birim tarafından değerlendirme yapılacaktır.\n\n"
            "Saygılarımla,"
        )
    if letter_type == "bilgilendirme":
        return (
            f"Sayın {route_name},\n\n"
            f"{subject} konusu kapsamında bilgilendirme yapılmıştır. "
            f"Belge içeriğinde yer alan hususların dikkate alınması ve gerekli işlemlerin yürütülmesi önem arz etmektedir.\n\n"
            "Saygılarımla,"
        )
    if letter_type == "üst_yazı":
        return (
            f"Sayın {route_name},\n\n"
            f"{subject} konusu ilişiğinde tarafımıza ulaştırılan evrak değerlendirilmiş olup, "
            "ilgili kurum/kuruluş bilgileri dikkate alınarak üst yazı kapsamında gerekli işlemler yapılacaktır.\n\n"
            "Saygılarımla,"
        )
    return (
        f"Sayın {route_name},\n\n"
        f"{subject} konusundaki talep/başvurunuz incelenmiş olup, aşağıdaki şekilde cevap verilmiştir.\n\n"
        f"{document[:300].strip()}\n\n"
        "Gerekli işlemler çerçevesinde tarafınıza dönüş sağlanacaktır.\n\n"
        "Saygılarımla,"
    )


def generate_draft(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise DraftError("payload must be an object")

    required_fields = ("document", "summary", "regulations", "routing", "missing_info")
    missing_fields = [field for field in required_fields if field not in payload]
    if missing_fields:
        raise DraftError(f"missing required fields: {', '.join(missing_fields)}")

    document = _as_string(payload.get("document"), "document")
    summary = _as_string(payload.get("summary"), "summary")
    regulations = _as_list(payload.get("regulations"), "regulations")
    routing = _as_string(payload.get("routing"), "routing")
    missing_info = _as_list(payload.get("missing_info"), "missing_info")

    if not regulations:
        regulations = ["İlgili mevzuat ve kurum içi prosedürler doğrultusunda işlem yapılacaktır."]

    subject = _normalize_subject(summary, document)
    letter_type = infer_letter_type(summary, missing_info, routing)
    if letter_type not in VALID_LETTER_TYPES:
        raise DraftError(f"unsupported letter type: {letter_type}")

    draft = render_draft(letter_type, subject, routing, document, missing_info)
    return {
        "letter_type": letter_type,
        "subject": subject,
        "draft": draft,
        "references": regulations,
    }
