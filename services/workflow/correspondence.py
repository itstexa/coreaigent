"""Deterministic F-04 retrieval selection, PII minimization, and output guards."""

from __future__ import annotations

import json
import re
import unicodedata

RETRIEVAL_CONFIG_VERSION = "municipality-rag-v1"
EMBEDDING_MODEL_ID = "BAAI/bge-m3"
EMBEDDING_DIMENSION = 1024
TOP_K = 5
MIN_COSINE_SIMILARITY = 0.60
MAX_SUMMARY_CHARACTERS = 600
MAX_DRAFT_CHARACTERS = 6000
MAX_TYPE_DETAIL_CHARACTERS = 200
MAX_CITATIONS = 5
MAX_CITATION_EXCERPT_CHARACTERS = 500
MAX_TOTAL_CITATION_EXCERPT_CHARACTERS = 2000
CORRESPONDENCE_TYPES = {"response_letter", "information_letter", "referral_letter", "cover_letter", "other"}
SEMANTIC_REPAIR_MIN_COSINE = 0.60
_FIELD_DESCRIPTIONS = {
    "document_summary": "başvuru belgesi kısa özet summary",
    "recommended_correspondence_type": "resmi yazışma türü correspondence type",
    "draft_text": "resmi yazışma taslak metni draft letter",
    "used_source_refs": "kullanılan kaynak atıf kimlikleri citation references",
}
_TYPE_DESCRIPTIONS = {
    "response_letter": "cevap yazısı response letter",
    "information_letter": "bilgilendirme yazısı information letter",
    "referral_letter": "yönlendirme sevk yazısı referral letter",
    "cover_letter": "üst yazı cover letter",
    "other": "diğer resmi yazışma other correspondence",
}


class NoSourceLegalClaimError(ValueError):
    """A draft without a retrieved source asserted an unsafe legal claim."""


def extract_json_object(model_response):
    """Read one JSON object from a Markdown/noisy model response without guessing text."""

    if not isinstance(model_response, str):
        raise ValueError("model response must be text")
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", model_response):
        try:
            value, _end = decoder.raw_decode(model_response[match.start():])
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("model response contains no JSON object")


def parse_generated_draft(model_response, *, retrieved_refs, source_status, similarity):
    """Validate one model answer, tolerating noise around its JSON object.

    A base instruct model can close a perfectly valid object and then keep
    typing, so the strict lane reads the first decodable object instead of the
    whole string.  Only a genuinely off-schema object falls through to
    semantic repair, which may relabel keys but never invents content.
    """

    payload = extract_json_object(model_response)
    try:
        return validate_generated_draft(payload, retrieved_refs, source_status)
    except NoSourceLegalClaimError:
        raise
    except ValueError:
        return semantic_repair_payload(payload, retrieved_refs=retrieved_refs, source_status=source_status, similarity=similarity)


def semantic_repair_payload(payload, *, retrieved_refs, source_status, similarity):
    """Map an otherwise valid object with semantically equivalent field names.

    `similarity` is the local BGE cosine scorer supplied by the worker.  It
    never invents text or citations: it only re-labels existing scalar values
    and accepts source references already supplied by retrieval.
    """

    if not isinstance(payload, dict):
        raise ValueError("structured output is not an object")
    candidates = sorted(
        (
            (float(similarity(str(key), description)), target, key)
            for target, description in _FIELD_DESCRIPTIONS.items()
            for key in payload
        ),
        reverse=True,
    )
    repaired = {}
    used_keys = set()
    for score, target, key in candidates:
        if score < SEMANTIC_REPAIR_MIN_COSINE:
            break
        if target not in repaired and key not in used_keys:
            repaired[target] = payload[key]
            used_keys.add(key)
    if "correspondence_type_detail" in payload:
        repaired["correspondence_type_detail"] = payload["correspondence_type_detail"]
    # The Turkish SFT checkpoint can return its source field name
    # `sanitized_document` instead of a document-summary key.  Selecting whole
    # already-generated sentences is a structural recovery, not a new model
    # claim; it remains subject to the ordinary summary limit and all guards.
    if "document_summary" not in repaired and isinstance(payload.get("sanitized_document"), str):
        summary = _whole_sentence_prefix(payload["sanitized_document"], MAX_SUMMARY_CHARACTERS)
        if summary:
            repaired["document_summary"] = summary
    if "recommended_correspondence_type" in repaired and repaired["recommended_correspondence_type"] not in CORRESPONDENCE_TYPES:
        label = str(repaired["recommended_correspondence_type"])
        choice, score = max(((type_id, float(similarity(label, description))) for type_id, description in _TYPE_DESCRIPTIONS.items()), key=lambda item: item[1])
        if score >= SEMANTIC_REPAIR_MIN_COSINE:
            repaired["recommended_correspondence_type"] = choice
    return validate_generated_draft(repaired, retrieved_refs, source_status)


def _whole_sentence_prefix(value, maximum):
    """Return complete existing sentences only; never synthesize or mid-cut text."""

    selected = []
    size = 0
    for sentence in re.split(r"(?<=[.!?])\s+", value.strip()):
        if not sentence or size + len(sentence) + (1 if selected else 0) > maximum:
            break
        selected.append(sentence)
        size += len(sentence) + (1 if len(selected) > 1 else 0)
    return " ".join(selected)


def build_retrieval_context(chunks):
    """Select only top-k chunks at the configured inclusive cosine threshold."""

    ranked = sorted(chunks, key=lambda item: (-float(item["score"]), item["chunk_id"]))[:TOP_K]
    selected = [item for item in ranked if float(item["score"]) >= MIN_COSINE_SIMILARITY]
    return ("relevant_source_found", selected) if selected else ("no_relevant_source", [])


def _placeholder(field_id):
    aliases = {"applicant-name": "APPLICANT_NAME", "supplier-name": "SUPPLIER_NAME", "tckn": "APPLICANT_TCKN", "phone": "PHONE", "applicant-address": "APPLICANT_ADDRESS"}
    return "{{" + aliases.get(field_id, field_id.replace("-", "_").upper()) + "}}"


def _normal_form(value):
    return re.sub(r"[^\w]+", "", unicodedata.normalize("NFC", value).casefold(), flags=re.UNICODE)


def _replace_known(source, field_id, value):
    if not isinstance(value, str) or not value.strip():
        return source
    placeholder = _placeholder(field_id)
    source = re.sub(re.escape(value), placeholder, source, flags=re.IGNORECASE)
    # Formatting-tolerant replacement deliberately handles only whitespace and
    # punctuation variants; it does not use edit-distance guesses over PII.
    pieces = [re.escape(part) for part in re.findall(r"\w+", value, flags=re.UNICODE)]
    if pieces:
        source = re.sub(r"[\W_]*".join(pieces), placeholder, source, flags=re.IGNORECASE)
    return source


def sanitize_text(source, *, known_values, field_handling):
    """Apply known-value and deterministic residual PII replacement.

    NER integration is a local optional adapter at the service edge; uncertain
    entity sentences must be removed there before reaching this deterministic
    core. This function has no network/model dependency.
    """

    result = unicodedata.normalize("NFC", source)
    for field_id, value in known_values.items():
        if field_handling.get(field_id, "redact") == "redact":
            result = _replace_known(result, field_id, value)
    patterns = (
        ("TCKN", r"(?<!\d)\d{11}(?!\d)"),
        ("PHONE", r"(?<!\d)(?:\+90|0)?5\d{9}(?!\d)"),
        ("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        ("IBAN", r"\bTR\d{2}(?:\s?\d{4}){5}\s?\d{2}\b"),
    )
    for label, pattern in patterns:
        counter = 0
        def replace(_match):
            nonlocal counter
            counter += 1
            return "{{REDACTED_" + label + "_" + str(counter) + "}}"
        result = re.sub(pattern, replace, result, flags=re.IGNORECASE)
    return result


def _assert_text(name, value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be non-blank and at most {maximum} characters")


def _has_unsafe_no_source_claim(text):
    citation_patterns = (
        r"\b\d{3,6}\s+sayılı\b",
        r"\bmadde\s+\d+\b",
        r"\b\d+\.\s*madde(?:si|sine|sinde|ye)?\b",
    )
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in citation_patterns):
        return True
    legal = r"(?:kanun\w*|yasa\w*|yönetmelik\w*|mevzuat\w*|tebliğ\w*|genelge\w*|madde\w*)"
    connector = r"(?:uyarınca|gereğince|göre|kapsamında|hükmü|uygun\s+olarak)"
    if re.search(legal + r"(?:\s+\S+){0,4}\s+" + connector, text, re.IGNORECASE):
        return True
    return bool(re.search(r"\b(?:zorunludur|yasaktır|kanunen mümkündür|yasal yükümlülüktür)\b|kurum\s+.+?\s+yükümlüdür", text, re.IGNORECASE))


def validate_generated_draft(payload, retrieved_refs, source_status):
    """Validate the closed Jamba result and return its canonical object."""

    allowed = {"document_summary", "recommended_correspondence_type", "correspondence_type_detail", "draft_text", "used_source_refs"}
    required = {"document_summary", "recommended_correspondence_type", "draft_text", "used_source_refs"}
    if not isinstance(payload, dict) or set(payload) - allowed or not required <= set(payload):
        raise ValueError("structured output schema is invalid")
    _assert_text("document_summary", payload["document_summary"], MAX_SUMMARY_CHARACTERS)
    _assert_text("draft_text", payload["draft_text"], MAX_DRAFT_CHARACTERS)
    correspondence_type = payload["recommended_correspondence_type"]
    if correspondence_type not in CORRESPONDENCE_TYPES:
        raise ValueError("correspondence type is invalid")
    detail = payload.get("correspondence_type_detail")
    if detail is not None and (correspondence_type != "other" or not isinstance(detail, str) or not detail.strip() or len(detail) > MAX_TYPE_DETAIL_CHARACTERS):
        raise ValueError("correspondence type detail is invalid")
    refs = payload["used_source_refs"]
    if not isinstance(refs, list) or len(refs) > MAX_CITATIONS or len(set(refs)) != len(refs) or not all(isinstance(ref, str) for ref in refs) or not set(refs) <= set(retrieved_refs):
        raise ValueError("used source refs are invalid")
    if source_status == "relevant_source_found" and not refs:
        raise ValueError("relevant source output must cite a retrieved chunk")
    if source_status == "no_relevant_source":
        if refs or retrieved_refs or _has_unsafe_no_source_claim(payload["draft_text"]):
            raise NoSourceLegalClaimError("no-source draft asserted an unverifiable legal claim")
    return payload
