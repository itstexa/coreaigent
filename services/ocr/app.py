import json
import os
import threading
import unicodedata
import uuid
from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb


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
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
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
        "language": "tr",
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
                        "(document_id, case_id, workflow_id, source_type, original_text, normalized_text, source_metadata, correlation_id, ingest_status) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'queued') "
                        "ON CONFLICT (document_id) DO NOTHING "
                        "RETURNING document_id, case_id, workflow_id, source_type, original_text, normalized_text, source_metadata, correlation_id, ingest_status",
                        (document_id, uuid.uuid4(), uuid.uuid4(), source_type, original_text, normalized_text, Jsonb(source_metadata), correlation_id),
                    )
                    record = cursor.fetchone()
                    if record is None:
                        cursor.execute(
                            "SELECT document_id, case_id, workflow_id, source_type, original_text, normalized_text, source_metadata, correlation_id, ingest_status "
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
