"""Public, dependency-free API for the Rule Engine baseline."""
from __future__ import annotations

from .rules import check_missing_fields, find_department, score_document_type, select_draft_type, suggest_legislation

def analyze_with_rules(document_text: str) -> dict:
    """Analyze a document and return a JSON-serializable baseline result.

    The score values are deterministic keyword-coverage heuristics, not
    probabilities or calibrated confidence values.
    """
    if not isinstance(document_text, str):
        raise TypeError("document_text must be a string")
    document_type, type_score = score_document_type(document_text)
    purpose = next((part.strip() for part in document_text.replace("\n", " ").split(".") if part.strip()), "")[:100]
    department, department_score = find_department(f"{purpose} {document_text}")
    missing_fields = check_missing_fields(document_text, document_type)
    draft_type = select_draft_type(document_type, department)
    draft = "\n".join((draft_type.upper(), "", "Sayı: [YAZIŞMA NUMARASI]", "Tarih: [BUGÜNÜN TARİHİ]", "", department, "", f"Konu: {purpose}", "", "Sayın Müdür,", "", f"{purpose} konusuyla ilgili başvuru incelemeye alınmıştır.", "", "Gereğini rica ederim.", "", "Saygılarımla,"))
    return {"document_type": document_type, "document_type_score": type_score, "purpose": purpose, "recommended_department": department, "department_score": department_score, "missing_fields": missing_fields, "legislation_suggestions": suggest_legislation(f"{purpose} {document_text}"), "draft_type": draft_type, "draft": draft, "notes": "document_type_score ve department_score, olasılık/confidence değil; anahtar kelime kapsama tabanlı heuristic skorlardır."}
