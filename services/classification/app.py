"""Deterministic, versioned taxonomy classification API for the F-02 demo."""

import json
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

try:  # ponytail: keep pure taxonomy tests stdlib-only; Docker installs FastAPI.
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
except ImportError:
    FastAPI = Request = JSONResponse = None


CLASSIFIER_VERSION = "demo-keyword-v1"
TAXONOMY_PATH = Path(os.environ.get("TAXONOMY_PATH", Path(__file__).with_name("taxonomy.json")))


def _text(value):
    return unicodedata.normalize("NFC", value).casefold()


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
            keywords = request_type.get("keywords")
            if not isinstance(request_type.get("label"), str) or not request_type["label"] or not isinstance(keywords, list) or not keywords:
                raise ValueError("request type label and keywords are required")
            normalized = [_text(keyword) for keyword in keywords if isinstance(keyword, str) and keyword]
            if len(normalized) != len(keywords) or len(set(normalized)) != len(normalized):
                raise ValueError("request type keywords must be non-empty and unique")
        return cls(mapping["taxonomyVersion"], departments, units, request_types)


def load_taxonomy(path=TAXONOMY_PATH):
    return Taxonomy.from_mapping(json.loads(Path(path).read_text(encoding="utf-8")))


def status_for_score(score):
    return "classified" if score > 0.80 else "needs_review"


def classify(text, taxonomy):
    normalized = _text(text)
    scored = []
    for request_type in taxonomy.request_types:
        keywords = [_text(value) for value in request_type["keywords"]]
        score = round(sum(keyword in normalized for keyword in keywords) / len(keywords), 3)
        scored.append((score, request_type["id"], request_type))
    score, _, request_type = sorted(scored, key=lambda item: (-item[0], item[1]))[0]
    if score == 0:
        return {"status": "needs_review", "department": None, "unit": None, "requestType": None, "confidence": 0.0}
    unit = taxonomy.units[request_type["unitId"]]
    department = taxonomy.departments[unit["departmentId"]]
    return {
        "status": status_for_score(score),
        "department": _node(department),
        "unit": _node(unit),
        "requestType": _node(request_type),
        "confidence": score,
    }


def classify_payload(payload, taxonomy):
    result = classify(payload["text"], taxonomy)
    reason = "No taxonomy keyword matched" if result["confidence"] == 0 else "Best matching taxonomy chain selected"
    return {
        "schemaVersion": "3.0",
        "requestId": payload["requestId"],
        "documentId": payload["documentId"],
        "workflowId": payload["workflowId"],
        **result,
        "taxonomyVersion": taxonomy.version,
        "classifierVersion": CLASSIFIER_VERSION,
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
