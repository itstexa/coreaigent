"""Deterministic, versioned taxonomy classification API for the F-02 demo."""

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

try:  # ponytail: keep pure taxonomy tests stdlib-only; Docker installs FastAPI.
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
except ImportError:
    FastAPI = Request = JSONResponse = None


# Two scoring models ship side by side.  `keyword-v2` is the original literal
# substring scorer whose acceptance criteria are frozen in US-107: a request
# type scores matched-keywords over keyword-count, so a five-keyword type only
# clears the 0.80 threshold when all five words appear literally.  That is the
# right model for a keyword-stuffed golden document and the wrong one for a
# petition a citizen actually writes, which mentions the subject two or three
# ways and never says "desibel".  `semantic-v3` scores concepts instead of
# words: each signal group holds the surface forms of one concept, three
# independent concepts are enough to decide, and matching is token- and
# suffix-aware so "gurultuden" and "gürültüsü" both count.
KEYWORD_CLASSIFIER_VERSION = "demo-keyword-v2"
SEMANTIC_CLASSIFIER_VERSION = "demo-semantic-v3"
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", "semantic-v3")
CLASSIFIER_VERSION = KEYWORD_CLASSIFIER_VERSION
TAXONOMY_PATH = Path(os.environ.get("TAXONOMY_PATH", Path(__file__).with_name("taxonomy.json")))

# How many distinct concepts must be present before the chain is trusted.  A
# free-text petition names its subject, its circumstance and its request; three
# is what a genuine petition carries without being written to please a scorer.
REQUIRED_SIGNALS = max(1, int(os.environ.get("REQUIRED_SIGNALS", "3") or 3))
# Prefix matching below this length would let "iz" match "izmir".
MIN_PREFIX_LENGTH = 4
EXACT_TOKEN_MARKER = "$"
_TOKEN_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)
# `"İ".casefold()` is "i" + U+0307, so a sentence-initial "İkamet" never
# contained the keyword "ikamet".  Dropping the combining dot after folding
# fixes the whole class of Turkish capital-I misses.
_COMBINING_DOT = "̇"
# Turkish keyboards are not a given: the same petition arrives as "gürültü",
# "gurultu" or "GÜRÜLTÜ".  The loose fold used by the concept model erases the
# difference on both sides of the comparison.
_ASCII_FOLD = str.maketrans({
    "ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c",
    "â": "a", "î": "i", "û": "u", "ê": "e", "ô": "o",
})


def _text(value):
    return unicodedata.normalize("NFC", value).casefold().replace(_COMBINING_DOT, "")


def _loose(value):
    return _text(value).translate(_ASCII_FOLD)


def _tokens(value):
    return tuple(_TOKEN_PATTERN.findall(_loose(value)))


# A request type may list its keywords as a plain list -- the original
# Turkish-only form -- or as one list per language.  Both stay supported: adding
# English must not renumber the Turkish denominator, because the score is matched
# keywords over list length and a merged list would halve every Turkish score.
DEFAULT_KEYWORD_LANGUAGE = "tr"


def keyword_sets(request_type):
    keywords = request_type.get("keywords")
    if isinstance(keywords, list):
        return {DEFAULT_KEYWORD_LANGUAGE: keywords}
    if isinstance(keywords, dict) and keywords:
        return keywords
    return {}


def _node(value):
    return {"id": value["id"], "label": value["label"]}


@dataclass(frozen=True)
class Taxonomy:
    version: str
    departments: dict
    units: dict
    request_types: tuple

    @classmethod
    def from_mapping(cls, mapping):
        if not isinstance(mapping, dict) or not isinstance(mapping.get("taxonomyVersion"), str) or not mapping["taxonomyVersion"]:
            raise ValueError("taxonomyVersion is required")
        departments = {item.get("id"): item for item in mapping.get("departments", []) if isinstance(item, dict)}
        units = {item.get("id"): item for item in mapping.get("units", []) if isinstance(item, dict)}
        request_types = tuple(item for item in mapping.get("requestTypes", []) if isinstance(item, dict))
        if not departments or not units or not request_types:
            raise ValueError("taxonomy must contain departments, units, and requestTypes")
        if len(departments) != len(mapping["departments"]) or len(units) != len(mapping["units"]):
            raise ValueError("taxonomy IDs must be unique")
        for department in departments.values():
            if not isinstance(department.get("label"), str) or not department["label"]:
                raise ValueError("department label is required")
        for unit in units.values():
            if unit.get("departmentId") not in departments:
                raise ValueError("unit departmentId must reference a department")
            if not isinstance(unit.get("label"), str) or not unit["label"]:
                raise ValueError("unit label is required")
        seen = set()
        for request_type in request_types:
            identifier = request_type.get("id")
            if not identifier or identifier in seen:
                raise ValueError("request type IDs must be unique")
            seen.add(identifier)
            if request_type.get("unitId") not in units:
                raise ValueError("request type unitId must reference a unit")
            languages = keyword_sets(request_type)
            if not isinstance(request_type.get("label"), str) or not request_type["label"] or not languages:
                raise ValueError("request type label and keywords are required")
            for language, keywords in languages.items():
                if not isinstance(language, str) or not language or not isinstance(keywords, list) or not keywords:
                    raise ValueError("request type keywords must be a non-empty list per language")
                normalized = [_text(keyword) for keyword in keywords if isinstance(keyword, str) and keyword]
                if len(normalized) != len(keywords) or len(set(normalized)) != len(normalized):
                    raise ValueError("request type keywords must be non-empty and unique")
        return cls(mapping["taxonomyVersion"], departments, units, request_types)


def load_taxonomy(path=TAXONOMY_PATH):
    return Taxonomy.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))


def status_for_score(score):
    return "classified" if score > 0.80 else "needs_review"


def _best_language(normalized, request_type):
    """Score the text against every language this request type is written for.

    The document's own detected language is deliberately not consulted: scoring
    each list separately and keeping the strongest match gives the same answer
    when detection succeeds and still classifies when it returns "unknown".
    """
    scored = []
    for language, values in sorted(keyword_sets(request_type).items()):
        keywords = [_text(value) for value in values]
        scored.append((round(sum(keyword in normalized for keyword in keywords) / len(keywords), 3), language))
    return max(scored, default=(0.0, DEFAULT_KEYWORD_LANGUAGE))


def classify(text, taxonomy):
    normalized = _text(text)
    scored = []
    for request_type in taxonomy.request_types:
        score, language = _best_language(normalized, request_type)
        scored.append((score, request_type["id"], request_type, language))
    score, _, request_type, language = sorted(scored, key=lambda item: (-item[0], item[1]))[0]
    if score == 0:
        return {"status": "needs_review", "department": None, "unit": None, "requestType": None, "confidence": 0.0, "keywordLanguage": None}
    unit = taxonomy.units[request_type["unitId"]]
    department = taxonomy.departments[unit["departmentId"]]
    return {
        "status": status_for_score(score),
        "department": _node(department),
        "unit": _node(unit),
        "requestType": _node(request_type),
        "confidence": score,
        "keywordLanguage": language,
    }


def classification_reason(result):
    """Say why this chain was chosen, naming the keyword list that matched.

    Which language matched is the one thing an operator cannot re-derive from the
    stored chain, and it is what tells them whether a low score means the wrong
    request type or the wrong language.
    """
    if result["confidence"] == 0:
        return "No taxonomy keyword matched"
    return f"Best matching taxonomy chain selected from {result['keywordLanguage']} keywords"


def signal_sets(request_type):
    """Concept groups per language, one group per independent signal.

    `signals` is optional: a request type that only carries `keywords` is read as
    one concept per keyword, so the concept model works on an untouched taxonomy
    and gets sharper for every type that spells its synonyms out.
    """
    signals = request_type.get("signals")
    if isinstance(signals, dict) and signals:
        groups = {}
        for language, listed in signals.items():
            if isinstance(listed, list) and listed:
                groups[language] = tuple(tuple(item) if isinstance(item, list) else (item,) for item in listed)
        if groups:
            return groups
    return {language: tuple((keyword,) for keyword in keywords) for language, keywords in keyword_sets(request_type).items()}


def _match_signal(group, tokens, text):
    """Return the surface form that carried this concept, or None.

    A multi-word form is looked for in the folded text; a single word matches a
    whole token or a token that starts with it, which is what Turkish
    agglutination needs ("gurultuden", "sikayetciyim") without a real stemmer
    inventing matches.

    Prefix matching misfires on short stems that are also the opening of an
    unrelated word -- "gece" opens "gecen", so "her gece" and "gecen ay" would
    count as the same signal.  A form written with a trailing `$` therefore
    matches whole tokens only, which is the taxonomy's way of saying "this stem
    takes no suffixes I want to follow".
    """
    for form in group:
        if not isinstance(form, str) or not form:
            continue
        exact = form.endswith(EXACT_TOKEN_MARKER)
        needle = _loose(form[: -len(EXACT_TOKEN_MARKER)] if exact else form)
        if not needle:
            continue
        if not needle.isalpha():
            if needle in text:
                return form
            continue
        for token in tokens:
            if token == needle:
                return form
            if not exact and len(needle) >= MIN_PREFIX_LENGTH and token.startswith(needle):
                return form
    return None


def signal_coverage(text, request_type):
    """Score one request type: concepts found over concepts needed.

    The denominator is `REQUIRED_SIGNALS`, not the group count, so listing more
    synonyms for a type can only help it.  Capping at 1.0 keeps the number
    comparable with the keyword model and with the frozen 0.80 threshold.
    """
    tokens, folded = _tokens(text), _loose(text)
    best = (0.0, (), DEFAULT_KEYWORD_LANGUAGE, 0, 0)
    for language, groups in sorted(signal_sets(request_type).items()):
        matched = tuple(form for form in (_match_signal(group, tokens, folded) for group in groups) if form)
        needed = min(REQUIRED_SIGNALS, len(groups)) or 1
        score = round(min(1.0, len(matched) / needed), 3)
        if (score, len(matched)) > (best[0], best[3]):
            best = (score, matched, language, len(matched), len(groups))
    return best


def classify_semantic(text, taxonomy):
    """Concept classification plus the evidence the decision rests on."""
    scored = []
    for request_type in taxonomy.request_types:
        score, matched, language, count, total = signal_coverage(text, request_type)
        scored.append((score, count, request_type["id"], request_type, matched, language, total))
    # Rank on the uncapped ratio: two types can both cap at 1.0, and the one
    # carrying four concepts is a better answer than the one carrying three.
    # The reported confidence stays capped so the frozen 0.80 threshold and the
    # keyword model keep meaning the same thing.
    ranked = sorted(scored, key=lambda item: (-item[1] / (min(REQUIRED_SIGNALS, item[6]) or 1), -item[1], item[2]))
    score, count, _, request_type, matched, language, total = ranked[0]
    runner_up = next(((item[3]["label"], item[0]) for item in ranked[1:] if item[0] > 0), None)
    evidence = {
        "language": language, "matched": matched, "needed": min(REQUIRED_SIGNALS, total) or 1,
        "signals": total, "runnerUp": runner_up,
    }
    if score == 0:
        return {"status": "needs_review", "department": None, "unit": None, "requestType": None, "confidence": 0.0, "keywordLanguage": None}, evidence
    unit = taxonomy.units[request_type["unitId"]]
    department = taxonomy.departments[unit["departmentId"]]
    return {
        "status": status_for_score(score),
        "department": _node(department),
        "unit": _node(unit),
        "requestType": _node(request_type),
        "confidence": score,
        "keywordLanguage": language,
    }, evidence


# Written in Turkish on purpose: this string is the explanation the citizen
# portal and the operator panel put in front of a person, and it is the only
# place the matched evidence survives the closed contract.
def semantic_reason(result, evidence):
    if result["confidence"] == 0:
        return "Metinde taksonomiye ait hiçbir konu sinyali bulunamadı; insan incelemesi gerekiyor."
    found = ", ".join(evidence["matched"]) or "-"
    detail = (
        f"Gereken {evidence['needed']} konu sinyalinden {len(evidence['matched'])} tanesi bulundu"
        f" ({evidence['language']} sinyal kümesi): {found}."
    )
    if evidence["runnerUp"]:
        label, score = evidence["runnerUp"]
        detail += f" En yakın alternatif: {label} (%{round(score * 100)})."
    if result["status"] == "needs_review":
        detail += " Güven eşiği aşılmadığı için sınıflandırma öneri olarak bırakıldı."
    return detail


def classify_document(text, taxonomy, model=None):
    """Run the configured scoring model and return (result, version, reason)."""
    if (model or CLASSIFIER_MODEL) == "keyword-v2":
        result = classify(text, taxonomy)
        return result, KEYWORD_CLASSIFIER_VERSION, classification_reason(result)
    result, evidence = classify_semantic(text, taxonomy)
    return result, SEMANTIC_CLASSIFIER_VERSION, semantic_reason(result, evidence)


def classify_payload(payload, taxonomy):
    result, classifier_version, reason = classify_document(payload["text"], taxonomy)
    # Which keyword list matched is an internal scoring detail; the contract is
    # closed, so it travels in the reason text rather than as a new field.
    return {
        "schemaVersion": "3.0",
        "requestId": payload["requestId"],
        "documentId": payload["documentId"],
        "workflowId": payload["workflowId"],
        **{key: value for key, value in result.items() if key != "keywordLanguage"},
        "taxonomyVersion": taxonomy.version,
        "classifierVersion": classifier_version,
        "classificationReason": reason,
    }


def valid_ocr_payload(payload):
    required = {"schemaVersion", "requestId", "documentId", "workflowId", "text", "language", "confidence", "ingestStatus", "warnings"}
    return (
        isinstance(payload, dict)
        and set(payload) == required | {"caseId"}
        and payload.get("schemaVersion") == "2.0"
        and all(isinstance(payload.get(field), str) and payload[field] for field in ("requestId", "documentId", "workflowId", "text"))
    )


def error(payload, status, category, message, retryable=False):
    source = payload if isinstance(payload, dict) else {}
    return JSONResponse(status_code=status, content={
        "schemaVersion": "2.0", "requestId": source.get("requestId") if isinstance(source.get("requestId"), str) else "unknown-request",
        "workflowId": source.get("workflowId") if isinstance(source.get("workflowId"), str) else None,
        "documentId": source.get("documentId") if isinstance(source.get("documentId"), str) else None,
        "service": "classification", "timestamp": "2026-01-01T00:00:00Z", "category": category,
        "message": message, "retryable": retryable,
    })


def create_app(taxonomy=None):
    if FastAPI is None:
        raise RuntimeError("FastAPI is required to serve classification HTTP")
    app = FastAPI(title="CoreAIgent classification")
    try:
        loaded = taxonomy or load_taxonomy()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        loaded, taxonomy_error = None, str(exc)
    else:
        taxonomy_error = None

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "classification"}

    @app.get("/ready")
    def ready():
        if taxonomy_error:
            return JSONResponse(status_code=503, content={"status": "not_ready", "service": "classification"})
        return {"status": "ready", "service": "classification", "taxonomyVersion": loaded.version}

    @app.post("/v1/classify")
    async def endpoint(request: Request):
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error({}, 400, "validation", "Invalid JSON")
        if not valid_ocr_payload(payload):
            return error(payload, 400, "validation", "Invalid ocr-result payload")
        if taxonomy_error:
            return error(payload, 503, "dependency", "Taxonomy is unavailable", True)
        return JSONResponse(content=classify_payload(payload, loaded))

    return app


app = create_app() if FastAPI is not None else None
