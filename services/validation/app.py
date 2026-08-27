"""Hybrid F-03 field validation primitives and HTTP service entry point."""

from __future__ import annotations

import calendar
import hashlib
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

try:
    import psycopg
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from psycopg.types.json import Jsonb
except ImportError:  # Pure rule tests intentionally remain stdlib-only.
    psycopg = FastAPI = Request = JSONResponse = Jsonb = None


@dataclass(frozen=True)
class FieldDefinition:
    field_id: str
    label: str
    kind: str
    required: bool


def normalized(value):
    return unicodedata.normalize("NFC", value).strip()


def valid_tckn(value):
    if not re.fullmatch(r"\d{11}", value) or value[0] == "0":
        return False
    digits = [int(digit) for digit in value]
    return ((sum(digits[0:9:2]) * 7 - sum(digits[1:8:2])) % 10 == digits[9] and sum(digits[:10]) % 10 == digits[10])


def validate_value(kind, raw_value, metadata):
    if not isinstance(raw_value, str):
        return None, "schema_rule"
    value = normalized(raw_value)
    if kind == "tckn":
        return (value, None) if valid_tckn(value) else (None, "tckn_checksum")
    if kind == "phone-tr":
        compact = re.sub(r"[ ()-]", "", value)
        digits = compact[3:] if compact.startswith("+90") else compact[1:] if compact.startswith("0") else compact
        return ("+90" + digits, None) if re.fullmatch(r"5\d{9}", digits) else (None, "phone_format")
    if kind == "date":
        try:
            parts = value.split("-") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else value.split(".")
            year, month, day = map(int, parts if len(parts[0]) == 4 else reversed(parts))
            if not 1 <= month <= 12 or not 1 <= day <= calendar.monthrange(year, month)[1]:
                raise ValueError
            return date(year, month, day).isoformat(), None
        except (TypeError, ValueError):
            return None, "date_format"
    if kind == "attachment":
        attachments = metadata.get("attachments") if isinstance(metadata, dict) else None
        if attachments is None:
            return None, None
        if not isinstance(attachments, list) or not 1 <= len(attachments) <= 64:
            return None, "attachment_missing"
        for item in attachments:
            if not isinstance(item, dict) or not isinstance(item.get("attachmentId"), str) or not 0 < len(normalized(item["attachmentId"])) <= 128:
                return None, "attachment_missing"
            if "filename" in item and (not isinstance(item["filename"], str) or not 1 <= len(normalized(item["filename"])) <= 255):
                return None, "attachment_missing"
            if "contentType" in item and (not isinstance(item["contentType"], str) or not item["contentType"].isascii() or not 1 <= len(item["contentType"]) <= 127):
                return None, "attachment_missing"
        return "present", None
    if not value or len(value) > 4096:
        return None, "schema_rule"
    if kind == "money-try" and not re.fullmatch(r"[1-9]\d*\.\d{2}", value):
        return None, "money_format"
    return value, None


def candidate_value(candidate):
    if isinstance(candidate, dict):
        return candidate.get("value"), candidate.get("confidence", 0.5)
    return candidate, 0.5


def evaluate_fields(definitions, candidates, existing, metadata):
    accepted, missing, invalid = [], [], []
    for definition in definitions:
        candidate, confidence = candidate_value(candidates.get(definition.field_id))
        if definition.kind == "attachment":
            candidate, confidence = "attachment", 1.0
        value, error = (None, None) if candidate is None else validate_value(definition.kind, candidate, metadata)
        prior = existing.get(definition.field_id)
        if error:
            invalid.append({"id": definition.field_id, "label": definition.label, "code": error})
            if prior:
                accepted.append({"id": definition.field_id, "label": definition.label, "value": prior["value"], "confidence": prior["confidence"]})
        elif value is not None:
            accepted.append({"id": definition.field_id, "label": definition.label, "value": value, "confidence": float(confidence)})
        elif prior:
            accepted.append({"id": definition.field_id, "label": definition.label, "value": prior["value"], "confidence": prior["confidence"]})
        elif definition.required:
            missing.append({"id": definition.field_id, "label": definition.label})
    status = "invalid_information" if invalid else "missing_information" if missing else "complete"
    return {"extractedFields": accepted, "missingRequiredFields": missing, "invalidFields": invalid, "completionStatus": status, "userActionRequired": status != "complete"}


def load_registry(path=Path(__file__).with_name("registry.json")):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schemaVersion") != "demo-belediyesi-fields-v1":
        raise ValueError("invalid registry version")
    registry = {}
    for request_type, fields in data.get("schemas", {}).items():
        definitions = tuple(FieldDefinition(item["id"], item["label"], item["kind"], item["required"]) for item in fields)
        if (not definitions or len(definitions) > 8 or len({item.field_id for item in definitions}) != len(definitions)
                or any(not re.fullmatch(r"[a-z][a-z0-9-]*", item.field_id) or not item.label or item.kind not in {"free-text", "tckn", "phone-tr", "date", "document-number", "money-try", "attachment"} or not isinstance(item.required, bool) for item in definitions)):
            raise ValueError("invalid field definitions")
        registry[request_type] = definitions
    if len(registry) != 10:
        raise ValueError("registry must define ten request types")
    return data["schemaVersion"], registry


DATABASE_URL = os.environ.get("DATABASE_URL", "")
AUTH_TOKEN = os.environ.get("CASE_ACCESS_TOKEN", "")
EXTRACTOR_MODE = os.environ.get("EXTRACTOR_MODE", "jamba")
JAMBA_URL = os.environ.get("JAMBA_URL", "http://llm:8080/generate")
# CUDA inference answers in seconds; the CPU overlay needs minutes, so the
# caller-side budget is configurable instead of hard-coded.
JAMBA_TIMEOUT_SECONDS = float(os.environ.get("JAMBA_TIMEOUT_SECONDS", "65") or 65)
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS intake_records (
    document_id text PRIMARY KEY, case_id uuid NOT NULL, workflow_id uuid NOT NULL,
    source_type text NOT NULL, original_text text NOT NULL, normalized_text text NOT NULL,
    source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb, correlation_id text NULL,
    ingest_status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE intake_records ADD COLUMN IF NOT EXISTS language text NOT NULL DEFAULT 'unknown';
CREATE TABLE IF NOT EXISTS current_classifications (
    document_id text PRIMARY KEY REFERENCES intake_records(document_id), case_id uuid NOT NULL, workflow_id uuid NOT NULL,
    status text NOT NULL, department_id text NULL, department_label text NULL, unit_id text NULL, unit_label text NULL,
    request_type_id text NULL, request_type_label text NULL, confidence numeric(4,3) NOT NULL,
    taxonomy_version text NOT NULL, classifier_version text NOT NULL, classification_reason text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS current_validation_states (
    case_id uuid PRIMARY KEY, document_id text NOT NULL UNIQUE REFERENCES intake_records(document_id), workflow_id uuid NOT NULL,
    request_type_id text NOT NULL, schema_version text NOT NULL, accepted_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
    missing_fields jsonb NOT NULL DEFAULT '[]'::jsonb, invalid_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
    completion_status text NOT NULL CHECK (completion_status IN ('complete', 'missing_information', 'invalid_information')),
    revision bigint NOT NULL CHECK (revision > 0), updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE current_validation_states ADD COLUMN IF NOT EXISTS current_correspondence_generation_id uuid NULL;
CREATE TABLE IF NOT EXISTS supplemental_replays (
    case_id uuid NOT NULL, idempotency_key uuid NOT NULL, request_fingerprint text NOT NULL,
    response_status integer NOT NULL, response_body jsonb NOT NULL, etag text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (case_id, idempotency_key)
);
"""


def error(body, status, category, message, retryable=False):
    payload = body if isinstance(body, dict) else {}
    return JSONResponse(status_code=status, content={"schemaVersion": "2.0", "requestId": payload.get("requestId", "unknown-request"), "workflowId": payload.get("workflowId"), "documentId": payload.get("documentId"), "service": "validation", "timestamp": "2026-08-25T00:00:00Z", "category": category, "message": message, "retryable": retryable})


def supplemental_error(status, category, message, retryable=False):
    return error({}, status, category, message, retryable)


def ensure_schema():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required")
    with psycopg.connect(DATABASE_URL, autocommit=True) as db:
        db.execute(SCHEMA_SQL)


def valid_classification(body):
    required = {"schemaVersion", "requestId", "documentId", "workflowId", "status", "department", "unit", "requestType", "confidence", "taxonomyVersion", "classifierVersion", "classificationReason"}
    return isinstance(body, dict) and set(body) == required and body.get("schemaVersion") == "3.0" and all(isinstance(body.get(key), str) and body[key] for key in ("requestId", "documentId", "workflowId"))


def rule_candidates(text):
    found = {}
    for key, pattern in (("tckn", r"(?<!\d)(\d{11})(?!\d)"), ("phone", r"(?<!\d)(?:\+90|0)?5\d{9}(?!\d)"), ("incident-date", r"(?<!\d)(?:\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})(?!\d)"), ("invoice-date", r"(?<!\d)(?:\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})(?!\d)")):
        match = re.search(pattern, text)
        if match:
            found[key] = {"value": match.group(1) if match.lastindex else match.group(0), "confidence": 1.0}
    return found


def labeled_candidates(text, definitions):
    candidates = rule_candidates(text)
    for definition in definitions:
        pattern = rf"(?im)^{re.escape(definition.field_id)}\s*:\s*(.+)$"
        match = re.search(pattern, text)
        if match:
            candidates[definition.field_id] = {"value": match.group(1).strip(), "confidence": 0.8}
    return candidates


def json_object(model_response):
    """Read one JSON object from a Markdown/noisy model response.

    A base instruct model routinely wraps its answer in a ```json fence or a
    sentence.  Scanning for the first decodable object keeps the extractor
    working without inventing values: key and type checks below still apply.
    """

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


# The instruction is written in the language of the document it is about.  A
# Turkish instruction over an English petition makes a base instruct model answer
# in Turkish, and here that means translating the applicant's own words before
# they are stored as extracted values -- so the wording follows the document.
# The field ids stay English in both, because they are the contract's keys.
EXTRACTION_INSTRUCTIONS = {
    "tr": (
        "Yalnız JSON object döndür. Anahtarlar sadece şu field id'ler olsun: {fields}."
        " Her değer metinden çıkarılmış string olsun; bulamadığını yazma. Metin:\n{text}"
    ),
    "en": (
        "Return only a JSON object. Use exactly these field ids as keys: {fields}."
        " Every value must be a string copied from the text; omit anything you cannot"
        " find. Do not translate the values. Text:\n{text}"
    ),
}
EXTRACTION_FALLBACK_LANGUAGE = "tr"


def extraction_prompt(text, semantic_definitions, language=None):
    """Build the F-03 instruction for the document's language.

    An unrecognised or absent language falls back to the authority's own
    language rather than guessing, which is the rule intake already applies.
    """
    template = EXTRACTION_INSTRUCTIONS.get(language) or EXTRACTION_INSTRUCTIONS[EXTRACTION_FALLBACK_LANGUAGE]
    return template.format(fields=", ".join(item.field_id for item in semantic_definitions), text=text)


def extract_candidates(text, definitions, language=None):
    if EXTRACTOR_MODE == "deterministic":
        return labeled_candidates(text, definitions)
    semantic_definitions = tuple(item for item in definitions if item.kind not in {"tckn", "phone-tr", "date", "attachment"})
    prompt = extraction_prompt(text, semantic_definitions, language)
    request = urllib.request.Request(JAMBA_URL, data=json.dumps({"prompt": prompt}, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=JAMBA_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
        semantic = json_object(payload["response"])
    except (KeyError, TypeError, ValueError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise RuntimeError("Jamba structured extraction is unavailable") from exc
    allowed = {item.field_id for item in semantic_definitions}
    if not isinstance(semantic, dict) or not set(semantic) <= allowed or not all(isinstance(value, str) for value in semantic.values()):
        raise RuntimeError("Jamba structured extraction returned invalid JSON")
    candidates = rule_candidates(text)
    candidates.update({key: {"value": value, "confidence": 0.5} for key, value in semantic.items()})
    return candidates


def validation_body(request_id, document_id, case_id, workflow_id, request_type_id, schema_version, evaluated):
    return {"schemaVersion": "3.0", "requestId": request_id, "documentId": document_id, "caseId": str(case_id), "workflowId": str(workflow_id), "requestTypeId": request_type_id, "schemaVersionUsed": schema_version, **evaluated}


def canonical_fields(evaluated):
    return {field["id"]: {"value": field["value"], "confidence": field["confidence"]} for field in evaluated["extractedFields"]}


def persist_validation(cursor, record, request_id, definitions, schema_version, candidates, existing=None):
    document_id, case_id, workflow_id, metadata, request_type_id = record
    existing = existing or {}
    evaluated = evaluate_fields(definitions, candidates, existing.get("accepted_fields", {}), metadata)
    fields = canonical_fields(evaluated)
    comparison = (fields, evaluated["missingRequiredFields"], evaluated["invalidFields"], evaluated["completionStatus"])
    if existing and comparison == (existing["accepted_fields"], existing["missing_fields"], existing["invalid_fields"], existing["completion_status"]):
        revision = existing["revision"]
    else:
        revision = (existing["revision"] + 1) if existing else 1
        cursor.execute("INSERT INTO current_validation_states (case_id, document_id, workflow_id, request_type_id, schema_version, accepted_fields, missing_fields, invalid_fields, completion_status, revision) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (case_id) DO UPDATE SET accepted_fields=EXCLUDED.accepted_fields, missing_fields=EXCLUDED.missing_fields, invalid_fields=EXCLUDED.invalid_fields, completion_status=EXCLUDED.completion_status, revision=EXCLUDED.revision, current_correspondence_generation_id=NULL, updated_at=now()", (case_id, document_id, workflow_id, request_type_id, schema_version, Jsonb(fields), Jsonb(evaluated["missingRequiredFields"]), Jsonb(evaluated["invalidFields"]), evaluated["completionStatus"], revision))
    return validation_body(request_id, document_id, case_id, workflow_id, request_type_id, schema_version, evaluated), revision


def create_app(registry=None):
    if FastAPI is None:
        raise RuntimeError("FastAPI and psycopg are required to serve validation HTTP")
    try:
        schema_version, loaded_registry = registry or load_registry()
        registry_error = None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        schema_version, loaded_registry, registry_error = None, {}, str(exc)
    app = FastAPI(title="CoreAIgent validation", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "validation"}

    @app.get("/ready")
    def ready():
        if registry_error or EXTRACTOR_MODE not in {"deterministic", "jamba"} or (EXTRACTOR_MODE == "jamba" and not JAMBA_URL):
            return JSONResponse(status_code=503, content={"status": "not_ready", "service": "validation"})
        try:
            ensure_schema()
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready", "service": "validation"})
        return {"status": "ready", "service": "validation", "schemaVersion": schema_version}

    @app.post("/v1/validate")
    async def validate(request: Request):
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error({}, 400, "validation", "Invalid JSON")
        if not valid_classification(body):
            return error(body, 400, "validation", "Invalid classification-result payload")
        if registry_error:
            return error(body, 503, "dependency", "Validation registry is unavailable", True)
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cursor:
                cursor.execute("SELECT r.document_id, r.case_id, r.workflow_id, r.source_metadata, c.request_type_id, c.status, r.normalized_text, r.language FROM intake_records r JOIN current_classifications c USING (document_id) WHERE r.document_id = %s FOR UPDATE", (body["documentId"],))
                row = cursor.fetchone()
                if not row:
                    return error(body, 404, "validation", "Document classification was not found")
                if row[5] != "classified" or row[4] not in loaded_registry:
                    return error(body, 409, "validation", "Document is not eligible for extraction")
                record, text, language = row[:5], row[6], row[7]
                cursor.execute("SELECT accepted_fields, missing_fields, invalid_fields, completion_status, revision FROM current_validation_states WHERE case_id = %s FOR UPDATE", (record[1],))
                state = cursor.fetchone()
                existing = None if not state else {"accepted_fields": state[0], "missing_fields": state[1], "invalid_fields": state[2], "completion_status": state[3], "revision": state[4]}
                result, revision = persist_validation(cursor, record, body["requestId"], loaded_registry[record[4]], schema_version, extract_candidates(text, loaded_registry[record[4]], language), existing)
        except RuntimeError:
            return error(body, 503, "dependency", "Jamba structured extraction is unavailable", True)
        except psycopg.Error:
            return error(body, 503, "dependency", "PostgreSQL is unavailable", True)
        return JSONResponse(content=result, headers={"ETag": f'"{revision}"'})

    @app.patch("/cases/{case_id}/supplemental-information")
    async def supplement(case_id: str, request: Request):
        if not AUTH_TOKEN or request.headers.get("Authorization") != f"Bearer {AUTH_TOKEN}":
            return supplemental_error(401, "authorization", "Bearer authorization is required")
        try:
            uuid.UUID(case_id)
        except ValueError:
            return supplemental_error(400, "validation", "case_id must be a UUID")
        idempotency_key, etag = request.headers.get("Idempotency-Key"), request.headers.get("If-Match")
        try:
            if not idempotency_key:
                return supplemental_error(400, "validation", "Idempotency-Key is required")
            uuid.UUID(idempotency_key)
        except ValueError:
            return supplemental_error(400, "validation", "Idempotency-Key must be a UUID")
        if not etag:
            return supplemental_error(428, "validation", "If-Match is required")
        if not re.fullmatch(r'"[1-9]\d*"', etag):
            return supplemental_error(400, "validation", "If-Match must be a quoted positive revision")
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return supplemental_error(400, "validation", "Invalid JSON")
        fields = body.get("fields") if isinstance(body, dict) and set(body) == {"fields"} else None
        if not isinstance(fields, dict) or not 1 <= len(fields) <= 8 or not all(isinstance(field_id, str) and isinstance(value, str) and normalized(value) and len(normalized(value)) <= 4096 for field_id, value in fields.items()):
            return supplemental_error(400, "validation", "fields must contain one to eight non-blank values")
        canonical_input = {normalized(field_id): normalized(value) for field_id, value in fields.items()}
        if len(canonical_input) != len(fields):
            return supplemental_error(400, "validation", "field IDs must remain unique after normalization")
        fingerprint = hashlib.sha256(json.dumps({"case": case_id, "method": "PATCH", "etag": etag, "fields": canonical_input}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cursor:
                cursor.execute("SELECT request_fingerprint, response_status, response_body, etag FROM supplemental_replays WHERE case_id = %s AND idempotency_key = %s FOR UPDATE", (case_id, idempotency_key))
                replay = cursor.fetchone()
                if replay:
                    if replay[0] != fingerprint:
                        return supplemental_error(409, "validation", "Idempotency-Key was used for a different request")
                    return JSONResponse(status_code=replay[1], content=replay[2], headers={"ETag": replay[3]})
                cursor.execute("SELECT s.document_id, s.case_id, s.workflow_id, r.source_metadata, s.request_type_id, s.accepted_fields, s.missing_fields, s.invalid_fields, s.completion_status, s.revision FROM current_validation_states s JOIN intake_records r USING (document_id) WHERE s.case_id = %s FOR UPDATE", (case_id,))
                state = cursor.fetchone()
                if not state:
                    return supplemental_error(404, "validation", "Case validation state was not found")
                if etag != f'"{state[9]}"':
                    return supplemental_error(412, "validation", "If-Match does not match the current revision")
                if any(field_id not in {definition.field_id for definition in loaded_registry[state[4]]} for field_id in canonical_input):
                    return supplemental_error(400, "validation", "fields contains an unknown field ID")
                existing = {"accepted_fields": state[5], "missing_fields": state[6], "invalid_fields": state[7], "completion_status": state[8], "revision": state[9]}
                result, revision = persist_validation(cursor, state[:5], "supplemental-" + idempotency_key, loaded_registry[state[4]], schema_version, canonical_input, existing)
                next_etag = f'"{revision}"'
                cursor.execute("INSERT INTO supplemental_replays (case_id, idempotency_key, request_fingerprint, response_status, response_body, etag) VALUES (%s,%s,%s,200,%s,%s)", (case_id, idempotency_key, fingerprint, Jsonb(result), next_etag))
        except psycopg.Error:
            return supplemental_error(503, "dependency", "PostgreSQL is unavailable", True)
        return JSONResponse(content=result, headers={"ETag": next_etag})

    return app


app = create_app() if FastAPI is not None else None
