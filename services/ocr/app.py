import json
import os
import re
import threading
import unicodedata
import uuid
from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb

from extraction import ExtractionError, extract_text


DATABASE_URL = os.environ.get("DATABASE_URL", "")
SCHEMA_LOCK = threading.Lock()
SCHEMA_READY = False

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS intake_records (
    document_id text PRIMARY KEY,
    case_id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    source_type text NOT NULL CHECK (source_type IN ('text', 'ocr')),
    original_text text NOT NULL,
    normalized_text text NOT NULL,
    source_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    correlation_id text NULL,
    ingest_status text NOT NULL CHECK (ingest_status = 'queued'),
    language text NOT NULL DEFAULT 'unknown',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
-- CREATE TABLE IF NOT EXISTS does nothing to a table that already exists, so a
-- column added after the first deployment needs its own idempotent statement.
ALTER TABLE intake_records ADD COLUMN IF NOT EXISTS language text NOT NULL DEFAULT 'unknown';
CREATE TABLE IF NOT EXISTS durable_outbox_jobs (
    job_id uuid PRIMARY KEY,
    document_id text NOT NULL UNIQUE REFERENCES intake_records(document_id),
    kind text NOT NULL CHECK (kind = 'process_document'),
    state text NOT NULL CHECK (state IN ('pending', 'claimed', 'completed')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    claimed_until timestamptz NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""

def _casefold(text):
    """Lowercase for comparison, keeping Turkish "İ" a plain dotted "i".

    Python's casefold turns "İ" into "i" plus a combining dot, which no longer
    matches a marker written as "ilgili".  Mapping the dotted capital first is
    the Turkish-correct lowercasing and is unambiguous: English never uses it.
    """
    return unicodedata.normalize("NFC", text.replace("İ", "i")).casefold()


# Intake is the only boundary that sees the applicant's own words, so it is where
# the document language is decided and recorded.  Downstream steps answer in that
# language instead of assuming Turkish, and the decision has to be reproducible:
# the same text must always yield the same language, on any host, with no model
# call and no extra dependency.
SUPPORTED_LANGUAGES = ("tr", "en")
FALLBACK_LANGUAGE = "tr"

# Function words carry the signal.  They appear in almost any real petition
# longer than a sentence, they are not shared between the two languages, and
# unlike content words they survive whatever the document is actually about.
LANGUAGE_MARKERS = {
    "tr": frozenset((
        "ve", "bir", "bu", "için", "ile", "olarak", "olan", "üzere", "tarafından",
        "gereğini", "arz", "ederim", "talep", "ediyorum", "değil", "daha", "sayın",
        "ilgili", "konu", "ancak", "veya", "şekilde", "kadar", "sonra", "önce",
        "adresinde", "tarihinde", "hakkında", "nedeniyle", "bulunan", "yapılan",
    )),
    "en": frozenset((
        "the", "and", "of", "to", "is", "are", "for", "with", "this", "that",
        "have", "has", "been", "would", "please", "regarding", "your", "our",
        "from", "which", "not", "was", "will", "there", "their", "at", "on",
        "in", "by", "as", "an", "be", "kindly", "request",
    )),
}
# Turkish orthography that English prose never needs.  Turkish place and person
# names ("Atatürk Street", "Kadıköy") appear inside English petitions, so only
# letters in words the author did not capitalize count: proper nouns are
# capitalized, ordinary Turkish prose is not.  A short Turkish sentence can carry
# no function word at all, so these letters have to be enough on their own.
TURKISH_LETTERS = frozenset("çğışöüÇĞİŞÖÜ")
MARKER_MARGIN = 1.25
TOKEN_PATTERN = r"[^0-9A-Za-zÀ-ÿĞğİıŞşÇçÖöÜü]+"


def _tokens(text):
    return [token for token in re.split(TOKEN_PATTERN, text) if token]


def _turkish_orthography(tokens):
    """Count lowercase words carrying a Turkish-only letter.

    A capitalized word is skipped because it is most likely a name, and names
    keep their spelling in whatever language the sentence around them is.
    """
    return sum(
        1
        for token in tokens
        if not token[0].isupper() and any(char in TURKISH_LETTERS for char in token)
    )


def detect_language(text):
    """Name the language a document is written in, or "unknown" when unsure.

    Only a Turkish/English mix-up actually costs anything: "unknown" falls back
    to the authority's own language downstream, so the rule is decisive when one
    language leads and abstains only when the two are genuinely close.
    """
    if not isinstance(text, str):
        return "unknown"
    tokens = _tokens(text)
    folded = [_casefold(token) for token in tokens]
    scores = {code: sum(token in markers for token in folded) for code, markers in LANGUAGE_MARKERS.items()}
    scores["tr"] += _turkish_orthography(tokens)
    leader, runner_up = sorted(scores, key=lambda code: (-scores[code], code))[:2]
    if scores[leader] < 1 or scores[leader] < MARKER_MARGIN * scores[runner_up]:
        return "unknown"
    return leader


app = FastAPI(title="CoreAIgent OCR intake")


def error(request_id, document_id, status, category, message, retryable):
    return JSONResponse(
        status_code=status,
        content={
            "schemaVersion": "2.0",
            "requestId": request_id if isinstance(request_id, str) and request_id else "unknown-request",
            "workflowId": None,
            "documentId": document_id if isinstance(document_id, str) and document_id else None,
            "service": "ocr",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "category": category,
            "message": message,
            "retryable": retryable,
        },
    )


def normalize(text):
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return "".join(char for char in text if char in "\t\n" or unicodedata.category(char) not in {"Cc", "Cf"})


def ensure_schema():
    global SCHEMA_READY
    if SCHEMA_READY:
        return
    if not DATABASE_URL:
        raise psycopg.OperationalError("DATABASE_URL is required")
    with SCHEMA_LOCK:
        if not SCHEMA_READY:
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                connection.execute(SCHEMA_SQL)
            SCHEMA_READY = True


def connection():
    ensure_schema()
    return psycopg.connect(DATABASE_URL)


def equal_record(record, source_type, original_text, normalized_text, source_metadata, correlation_id):
    return (
        record[3] == source_type
        and record[4] == original_text
        and record[5] == normalized_text
        and record[6] == source_metadata
        and record[7] == correlation_id
    )


def result(request_id, record):
    return {
        "schemaVersion": "2.0",
        "requestId": request_id,
        "documentId": record[0],
        "caseId": str(record[1]),
        "workflowId": str(record[2]),
        "text": record[5],
        "language": record[9],
        "confidence": 1.0,
        "ingestStatus": record[8],
        "warnings": [],
    }


def valid_payload(payload):
    allowed = {"schemaVersion", "requestId", "documentId", "sourceType", "text", "sourceMetadata", "correlationId"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        return "Invalid request fields"
    if payload.get("schemaVersion") != "2.0":
        return "schemaVersion must be 2.0"
    for field in ("requestId", "documentId"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            return f"{field} must be a non-empty string"
    if payload.get("sourceType") not in {"text", "ocr"}:
        return "sourceType must be text or ocr"
    if not isinstance(payload.get("text"), str):
        return "text must be a string"
    if "sourceMetadata" in payload and not isinstance(payload["sourceMetadata"], dict):
        return "sourceMetadata must be an object"
    if "correlationId" in payload and payload["correlationId"] is not None and not isinstance(payload["correlationId"], str):
        return "correlationId must be a string or null"
    return None


@app.get("/health")
def health():
    return {"status": "ok", "service": "ocr"}


@app.get("/ready")
def ready():
    try:
        ensure_schema()
        with psycopg.connect(DATABASE_URL) as db:
            db.execute("SELECT 1")
    except psycopg.Error:
        return JSONResponse(status_code=503, content={"status": "not_ready", "service": "ocr"})
    return {"status": "ready", "service": "ocr"}


@app.post("/v1/ocr")
async def intake(request: Request):
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return error(None, None, 400, "validation", "Invalid JSON", False)

    request_id = payload.get("requestId") if isinstance(payload, dict) else None
    document_id = payload.get("documentId") if isinstance(payload, dict) else None
    validation_error = valid_payload(payload)
    if validation_error:
        return error(request_id, document_id, 400, "validation", validation_error, False)

    original_text = payload["text"]
    normalized_text = normalize(original_text)
    if not normalized_text.strip() or len(normalized_text) < 40:
        return error(request_id, document_id, 400, "validation", "text must contain at least 40 normalized characters", False)

    source_type = payload["sourceType"]
    source_metadata = payload.get("sourceMetadata", {})
    correlation_id = payload.get("correlationId")
    try:
        with connection() as db:
            with db.cursor() as cursor:
                with db.transaction():
                    cursor.execute(
                        "INSERT INTO intake_records "
                        "(document_id, case_id, workflow_id, source_type, original_text, normalized_text, source_metadata, correlation_id, ingest_status, language) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'queued', %s) "
                        "ON CONFLICT (document_id) DO NOTHING "
                        "RETURNING document_id, case_id, workflow_id, source_type, original_text, normalized_text, source_metadata, correlation_id, ingest_status, language",
                        (document_id, uuid.uuid4(), uuid.uuid4(), source_type, original_text, normalized_text, Jsonb(source_metadata), correlation_id, detect_language(normalized_text)),
                    )
                    record = cursor.fetchone()
                    if record is None:
                        cursor.execute(
                            "SELECT document_id, case_id, workflow_id, source_type, original_text, normalized_text, source_metadata, correlation_id, ingest_status, language "
                            "FROM intake_records WHERE document_id = %s",
                            (document_id,),
                        )
                        record = cursor.fetchone()
                        if not equal_record(record, source_type, original_text, normalized_text, source_metadata, correlation_id):
                            return error(request_id, document_id, 409, "validation", "documentId conflicts with immutable intake data", False)
                    else:
                        cursor.execute(
                            "INSERT INTO durable_outbox_jobs (job_id, document_id, kind, state, attempt_count) "
                            "VALUES (%s, %s, 'process_document', 'pending', 0)",
                            (uuid.uuid4(), document_id),
                        )
    except psycopg.Error:
        return error(request_id, document_id, 503, "dependency", "PostgreSQL is unavailable", True)

    return result(request_id, record)


@app.post("/v1/extract-text")
async def extract_uploaded_text(request: Request):
    """Convert one PDF/DOCX without creating intake or corpus state."""
    try:
        form = await request.form(max_files=1, max_fields=4)
        request_id, purpose = form.get("requestId"), form.get("purpose")
        upload = form.get("file")
        if not isinstance(request_id, str) or not request_id or purpose not in {"rag_source", "case_attachment"} or upload is None:
            return error(request_id if isinstance(request_id, str) else None, None, 400, "validation", "requestId, purpose, and file are required", False)
        content = await upload.read(10 * 1024 * 1024 + 1)
        text = normalize(extract_text(upload.filename, upload.content_type, content))
        if len(text) < 40:
            return error(request_id, None, 422, "validation", "EXTRACTED_TEXT_TOO_SHORT", False)
    except ExtractionError as exc:
        status = 503 if exc.code in {"OCR_MODEL_UNAVAILABLE", "OCR_BUSY"} else 422
        return error(None, None, status, "dependency" if status == 503 else "validation", exc.code, status == 503)
    return {"schemaVersion": "2.0", "requestId": request_id, "filename": upload.filename, "contentType": upload.content_type, "purpose": purpose, "text": text}
