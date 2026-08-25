"""F-04 case-level correspondence API backed by PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb

DATABASE_URL = os.environ.get("DATABASE_URL", "")
AUTH_TOKEN = os.environ.get("CASE_ACCESS_TOKEN", "")
CORPUS_VERSION = "demo-municipality-regulations-v1"
PROMPT_SCHEMA_VERSION = "f04-correspondence-v1"

SCHEMA_SQL = """
ALTER TABLE current_validation_states ADD COLUMN IF NOT EXISTS current_correspondence_generation_id uuid NULL;
CREATE TABLE IF NOT EXISTS correspondence_generations (
 generation_id uuid PRIMARY KEY, case_id uuid NOT NULL, document_id text NOT NULL, workflow_id uuid NOT NULL,
 source_case_revision bigint NOT NULL CHECK (source_case_revision > 0), request_type_id text NOT NULL,
 department_label text NOT NULL, unit_label text NOT NULL, corpus_version text NOT NULL,
 retrieval_config_version text NOT NULL, prompt_schema_version text NOT NULL, validated_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
 model_id text NULL, model_revision text NULL, generation_status text NOT NULL CHECK (generation_status IN ('queued','processing','completed','failed')),
 source_status text NULL CHECK (source_status IN ('relevant_source_found','no_relevant_source')),
 result_status text NULL CHECK (result_status IN ('draft_ready','review_required')),
 correspondence_type text NULL CHECK (correspondence_type IN ('response_letter','information_letter','referral_letter','cover_letter','other')),
 correspondence_type_detail text NULL, document_summary text NULL, draft_text text NULL,
 regulation_suggestions jsonb NOT NULL DEFAULT '[]'::jsonb, model_attempt_count smallint NOT NULL DEFAULT 0 CHECK (model_attempt_count BETWEEN 0 AND 2),
 error_code text NULL, created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz NULL
);
ALTER TABLE correspondence_generations ADD COLUMN IF NOT EXISTS validated_fields jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE TABLE IF NOT EXISTS correspondence_generation_jobs (
 job_id uuid PRIMARY KEY, generation_id uuid NOT NULL UNIQUE REFERENCES correspondence_generations(generation_id),
 state text NOT NULL CHECK (state IN ('pending','claimed','completed')), attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
 claimed_until timestamptz NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS correspondence_replays (
 principal_id text NOT NULL, case_id uuid NOT NULL, idempotency_key uuid NOT NULL, source_case_revision bigint NOT NULL,
 request_fingerprint text NOT NULL, generation_id uuid NOT NULL REFERENCES correspondence_generations(generation_id), job_id uuid NOT NULL REFERENCES correspondence_generation_jobs(job_id),
 response_status integer NOT NULL, response_body jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (principal_id, case_id, idempotency_key)
);
"""


def nested_error(status, code, message, **extra):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


def _authorized(request):
    return bool(AUTH_TOKEN) and request.headers.get("Authorization") == f"Bearer {AUTH_TOKEN}"


def _headers(request):
    key, etag = request.headers.get("Idempotency-Key"), request.headers.get("If-Match")
    if not key:
        return None, None, nested_error(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key is required")
    try:
        uuid.UUID(key)
    except ValueError:
        return None, None, nested_error(400, "IDEMPOTENCY_KEY_INVALID", "Idempotency-Key must be a UUID")
    if not etag:
        return None, None, nested_error(428, "IF_MATCH_REQUIRED", "If-Match is required")
    if not re.fullmatch(r'"[1-9]\d*"', etag):
        return None, None, nested_error(400, "IF_MATCH_INVALID", "If-Match must be a quoted positive revision")
    return key, int(etag[1:-1]), None


def ensure_schema():
    with psycopg.connect(DATABASE_URL, autocommit=True) as db:
        db.execute(SCHEMA_SQL)


def create_app():
    app = FastAPI(title="CoreAIgent workflow", docs_url=None, redoc_url=None)

    @app.on_event("startup")
    def initialize_persistence():
        # The worker may start before its first HTTP readiness probe.  Create
        # the durable F-04 tables as part of API startup, not as a side effect
        # of /ready.
        ensure_schema()

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "workflow"}

    @app.get("/ready")
    def ready():
        try:
            ensure_schema()
        except psycopg.Error:
            return JSONResponse(status_code=503, content={"status": "not_ready", "service": "workflow"})
        return {"status": "ready", "service": "workflow"}

    @app.post("/cases/{case_id}/correspondence")
    async def start(case_id: str, request: Request):
        if not _authorized(request):
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        try:
            case = uuid.UUID(case_id)
        except ValueError:
            return nested_error(400, "CASE_ID_INVALID", "case_id must be a UUID")
        key, expected_revision, bad = _headers(request)
        if bad:
            return bad
        raw = await request.body()
        if raw:
            try:
                body = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return nested_error(400, "REQUEST_BODY_INVALID", "Body must be empty or {}")
            if body != {}:
                return nested_error(400, "REQUEST_BODY_INVALID", "Client generation input is not allowed")
        principal = "case-access-token"  # credential itself is never persisted
        fingerprint = hashlib.sha256(json.dumps({"case_id": case_id, "revision": expected_revision, "method": "POST", "body": {}}, sort_keys=True).encode()).hexdigest()
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                cur.execute("SELECT request_fingerprint, response_status, response_body FROM correspondence_replays WHERE principal_id=%s AND case_id=%s AND idempotency_key=%s FOR UPDATE", (principal, case, key))
                replay = cur.fetchone()
                if replay:
                    if replay[0] != fingerprint:
                        return nested_error(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was used for another revision")
                    return JSONResponse(status_code=replay[1], content=replay[2])
                cur.execute("SELECT s.document_id,s.workflow_id,s.request_type_id,s.completion_status,s.revision,c.department_label,c.unit_label,s.accepted_fields FROM current_validation_states s JOIN current_classifications c USING (document_id) WHERE s.case_id=%s FOR UPDATE", (case,))
                state = cur.fetchone()
                if not state:
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                if state[4] != expected_revision:
                    return nested_error(412, "CASE_REVISION_CONFLICT", "If-Match does not match current case revision")
                if state[3] != "complete":
                    return nested_error(409, "CASE_NOT_READY_FOR_CORRESPONDENCE", "Case requires additional or corrected information.", case_state="waiting_for_user", completion_status=state[3])
                generation, job = uuid.uuid4(), uuid.uuid4()
                cur.execute("INSERT INTO correspondence_generations (generation_id,case_id,document_id,workflow_id,source_case_revision,request_type_id,department_label,unit_label,corpus_version,retrieval_config_version,prompt_schema_version,validated_fields,generation_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'municipality-rag-v1',%s,%s,'queued')", (generation, case, state[0], state[1], expected_revision, state[2], state[5], state[6], CORPUS_VERSION, PROMPT_SCHEMA_VERSION, Jsonb(state[7])))
                cur.execute("INSERT INTO correspondence_generation_jobs (job_id,generation_id,state) VALUES (%s,%s,'pending')", (job, generation))
                cur.execute("UPDATE current_validation_states SET current_correspondence_generation_id=%s WHERE case_id=%s AND revision=%s", (generation, case, expected_revision))
                response = {"case_id": case_id, "job_id": str(job), "case_revision": expected_revision, "generation_status": "queued"}
                cur.execute("INSERT INTO correspondence_replays (principal_id,case_id,idempotency_key,source_case_revision,request_fingerprint,generation_id,job_id,response_status,response_body) VALUES (%s,%s,%s,%s,%s,%s,%s,202,%s)", (principal, case, key, expected_revision, fingerprint, generation, job, Jsonb(response)))
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return JSONResponse(status_code=202, content=response)

    @app.get("/cases/{case_id}/correspondence")
    def read(case_id: str, request: Request):
        if not _authorized(request):
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        try:
            case = uuid.UUID(case_id)
            with psycopg.connect(DATABASE_URL) as db:
                state = db.execute("SELECT revision,current_correspondence_generation_id FROM current_validation_states WHERE case_id=%s", (case,)).fetchone()
                if not state:
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                base = {"case_id": case_id, "case_revision": state[0]}
                if not state[1]:
                    return base | {"generation_status": "not_requested", "result": None}
                row = db.execute("SELECT generation_id,generation_status,source_status,result_status,corpus_version,document_summary,correspondence_type,correspondence_type_detail,draft_text,regulation_suggestions,error_code FROM correspondence_generations WHERE generation_id=%s", (state[1],)).fetchone()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        if row[1] in {"queued", "processing"}:
            return base | {"generation_status": row[1]}
        if row[1] == "failed":
            return base | {"generation_id": str(row[0]), "generation_status": "failed", "error_code": row[10]}
        return base | {"generation_id": str(row[0]), "generation_status": "completed", "source_status": row[2], "result_status": row[3], "corpus_version": row[4], "document_summary": row[5], "recommended_correspondence_type": row[6], "correspondence_type_detail": row[7], "draft_text": row[8], "regulation_suggestions": row[9]}

    return app


app = create_app()
