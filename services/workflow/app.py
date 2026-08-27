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
ADMIN_TOKEN = os.environ.get("CASE_ADMIN_TOKEN", "")
CORPUS_VERSION = "demo-municipality-regulations-v1"
PROMPT_SCHEMA_VERSION = "f04-correspondence-v1"

SCHEMA_SQL = """
DO $$ BEGIN
 IF to_regclass('public.current_validation_states') IS NOT NULL THEN
  ALTER TABLE current_validation_states ADD COLUMN IF NOT EXISTS current_correspondence_generation_id uuid NULL;
 END IF;
END $$;
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
CREATE TABLE IF NOT EXISTS routing_operations (
 routing_id uuid PRIMARY KEY, case_id uuid NOT NULL, source_case_revision bigint NOT NULL CHECK (source_case_revision > 0),
 source_generation_id uuid NULL REFERENCES correspondence_generations(generation_id), request_type_id text NOT NULL,
 route_kind text NOT NULL CHECK (route_kind IN ('classified','fallback')),
 target_department_id text NOT NULL, target_department_label text NOT NULL, target_unit_id text NOT NULL, target_unit_label text NOT NULL,
 taxonomy_version text NOT NULL, routing_status text NOT NULL CHECK (routing_status IN ('routed','failed')),
 routing_reason jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(), routed_at timestamptz NULL,
 UNIQUE (case_id, source_case_revision)
);
CREATE TABLE IF NOT EXISTS routing_jobs (
 job_id uuid PRIMARY KEY, case_id uuid NOT NULL, source_case_revision bigint NOT NULL CHECK (source_case_revision > 0),
 source_generation_id uuid NULL REFERENCES correspondence_generations(generation_id), recovery_reason text NULL,
 state text NOT NULL CHECK (state IN ('pending','claimed','completed','rejected')), attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
 claimed_until timestamptz NULL, rejection_code text NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (case_id, source_case_revision)
);
CREATE TABLE IF NOT EXISTS notification_records (
 notification_id uuid PRIMARY KEY, routing_id uuid NOT NULL REFERENCES routing_operations(routing_id),
 audience text NOT NULL CHECK (audience IN ('applicant','target_unit')),
 generation_status text NOT NULL CHECK (generation_status IN ('queued','processing','completed','failed')),
 payload jsonb NULL, model_id text NULL, model_revision text NULL,
 attempt_count smallint NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 2), error_code text NULL,
 created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz NULL, UNIQUE (routing_id, audience)
);
CREATE TABLE IF NOT EXISTS notification_jobs (
 job_id uuid PRIMARY KEY, notification_id uuid NOT NULL UNIQUE REFERENCES notification_records(notification_id),
 state text NOT NULL CHECK (state IN ('pending','claimed','completed')), attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
 claimed_until timestamptz NULL, rejection_code text NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS current_case_states (
 case_id uuid PRIMARY KEY, revision bigint NOT NULL CHECK (revision > 0),
 state text NOT NULL CHECK (state IN ('received','normalized','classified','needs_review','extracting','waiting_for_user','ready_for_processing','draft_prepared','routed','notification_pending','completed','failed')),
 completed_steps jsonb NOT NULL DEFAULT '[]'::jsonb, last_error_code text NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS correspondence_start_jobs (
 job_id uuid PRIMARY KEY, case_id uuid NOT NULL, source_case_revision bigint NOT NULL CHECK (source_case_revision > 0),
 state text NOT NULL CHECK (state IN ('pending','claimed','waiting','completed','failed')),
 attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 4),
 next_attempt_at timestamptz NULL, claimed_until timestamptz NULL, error_code text NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (case_id, source_case_revision)
);
CREATE TABLE IF NOT EXISTS case_notifications (
 notification_id uuid PRIMARY KEY, case_id uuid NOT NULL, source_case_revision bigint NOT NULL CHECK (source_case_revision > 0),
 audience text NOT NULL CHECK (audience='applicant'), kind text NOT NULL CHECK (kind IN ('missing_information','invalid_information')),
 payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (case_id, source_case_revision, audience, kind)
);
CREATE TABLE IF NOT EXISTS review_completion_replays (
 case_id uuid NOT NULL, idempotency_key uuid NOT NULL, source_case_revision bigint NOT NULL,
 response_body jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (case_id,idempotency_key)
);
"""


def nested_error(status, code, message, **extra):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


def _authorized(request):
    return bool(AUTH_TOKEN) and request.headers.get("Authorization") == f"Bearer {AUTH_TOKEN}"


def _role(request):
    value = request.headers.get("Authorization")
    if AUTH_TOKEN and value == f"Bearer {AUTH_TOKEN}":
        return "USER"
    if ADMIN_TOKEN and value == f"Bearer {ADMIN_TOKEN}":
        return "ADMIN"
    return None


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
    # PostgreSQL's `CREATE TABLE IF NOT EXISTS` is not safe against two fresh
    # containers concurrently creating the same composite type.  The API and
    # workers therefore serialize first boot without introducing another
    # dependency or losing a durable job.
    with psycopg.connect(DATABASE_URL, autocommit=True) as db:
        db.execute("SELECT pg_advisory_lock(hashtext('coreaigent-workflow-schema-v1'))")
        try:
            db.execute(SCHEMA_SQL)
        finally:
            db.execute("SELECT pg_advisory_unlock(hashtext('coreaigent-workflow-schema-v1'))")


def _case_uuid(case_id):
    """Reject a non-UUID path segment before it reaches PostgreSQL.

    `uuid.UUID` raises ValueError, and the read handlers only guard against
    psycopg errors, so a stale client id used to surface as an opaque 500 for
    what is plainly a bad request.
    """
    try:
        return uuid.UUID(case_id), None
    except ValueError:
        return None, nested_error(400, "CASE_ID_INVALID", "case_id must be a UUID")


# The applicant is named by whichever field the request type's schema defines
# for it; the admin list shows one column, so the first present key wins.
APPLICANT_NAME_KEYS = ("applicant-name", "business-name", "supplier-name")
CASE_LIST_MAX_LIMIT = 100


def _accepted_value(accepted_fields, key):
    entry = (accepted_fields or {}).get(key)
    if isinstance(entry, dict):
        value = entry.get("value")
        return value if isinstance(value, str) and value else None
    return entry if isinstance(entry, str) and entry else None


def _applicant_name(accepted_fields):
    for key in APPLICANT_NAME_KEYS:
        value = _accepted_value(accepted_fields, key)
        if value:
            return value
    return None


def _metadata_text(metadata, key):
    value = (metadata or {}).get(key)
    return value if isinstance(value, str) and value else None


def case_list_item(row):
    """Project one admin list row.

    Kept pure and separate from the query so the shape stays testable without a
    database, and so a case that never reached F-03 -- classification wrote a
    projection but validation never ran -- still lists with null field values
    instead of being dropped from the operator's queue.
    """
    (case_id, revision, state, completed_steps, last_error_code, updated_at, completion_status,
     document_id, request_type_id, accepted_fields, department_id, department_label, unit_id,
     unit_label, request_type_label, classification_status, confidence, routing_status,
     created_at, language, source_metadata, classification_reason) = row
    return {
        "case_id": str(case_id),
        "case_revision": revision,
        "state": state,
        "completed_steps": completed_steps or [],
        "last_error_code": last_error_code,
        "updated_at": updated_at.isoformat(),
        "validation_status": completion_status,
        "routing_status": routing_status or "not_routed",
        "document_id": document_id,
        "request_type_id": request_type_id,
        "request_type_label": request_type_label,
        "department_id": department_id,
        "department_label": department_label,
        "unit_id": unit_id,
        "unit_label": unit_label,
        "classification_status": classification_status,
        "classification_confidence": None if confidence is None else float(confidence),
        # The reason the classifier gives is the only human-readable account of
        # why this case sits in this unit.  Without it in the list the panel can
        # show a label and a percentage but cannot answer "why", which is the
        # first question an operator asks about an automatic decision.
        "classification_reason": classification_reason,
        "applicant_name": _applicant_name(accepted_fields),
        "title": _metadata_text(source_metadata, "title"),
        "channel": _metadata_text(source_metadata, "channel"),
        "language": language,
        "created_at": None if created_at is None else created_at.isoformat(),
    }


def case_document_item(case_id, record):
    """Project the intake row the panel reads a petition from.

    Pure so the projection can be falsified without a database, the same way the
    list row can.
    """
    document_id, source_type, original_text, language, source_metadata, created_at = record
    return {
        "case_id": str(case_id),
        "document_id": document_id,
        "source_type": source_type,
        "language": language,
        "title": _metadata_text(source_metadata, "title"),
        "channel": _metadata_text(source_metadata, "channel"),
        "created_at": created_at.isoformat(),
        "text": original_text or "",
    }


def case_list_bounds(limit, offset):
    """Clamp paging input instead of trusting or rejecting it.

    A list view is read-only and non-destructive; an out-of-range page is a
    client bug, not an incident, so it collapses to the nearest legal window.
    """
    try:
        size = int(limit)
    except (TypeError, ValueError):
        size = 25
    try:
        start = int(offset)
    except (TypeError, ValueError):
        start = 0
    return max(1, min(size, CASE_LIST_MAX_LIMIT)), max(0, start)


CASE_LIST_SQL = (
    "SELECT cs.case_id,cs.revision,cs.state,cs.completed_steps,cs.last_error_code,cs.updated_at,"
    "s.completion_status,COALESCE(s.document_id,c.document_id),COALESCE(s.request_type_id,c.request_type_id),"
    "s.accepted_fields,c.department_id,c.department_label,c.unit_id,c.unit_label,c.request_type_label,"
    "c.status,c.confidence,r.routing_status,i.created_at,i.language,i.source_metadata,c.classification_reason "
    "FROM current_case_states cs "
    "LEFT JOIN current_validation_states s ON s.case_id=cs.case_id "
    "LEFT JOIN current_classifications c ON c.case_id=cs.case_id "
    "LEFT JOIN routing_operations r ON r.case_id=cs.case_id AND r.source_case_revision=cs.revision "
    "LEFT JOIN intake_records i ON i.case_id=cs.case_id "
)


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

    @app.get("/cases")
    def case_list(request: Request, limit: int = 25, offset: int = 0, state: str = "", q: str = ""):
        """Operator queue of every projected case, newest change first.

        The browser used to keep its own list in local storage, which meant a
        case submitted from one device was invisible to the operator on another.
        This is the authoritative list, and it stays ADMIN-only because it
        aggregates applicant names and unit routing across cases -- data the
        USER token is deliberately never shown even for a single case.
        """
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        if role != "ADMIN":
            return nested_error(403, "FORBIDDEN", "ADMIN authorization is required")
        size, start = case_list_bounds(limit, offset)
        clauses, params = [], []
        if state:
            clauses.append("cs.state=%s")
            params.append(state)
        if q:
            needle = f"%{q}%"
            clauses.append(
                "(COALESCE(s.document_id,c.document_id) ILIKE %s OR cs.case_id::text ILIKE %s"
                " OR COALESCE(c.request_type_label,'') ILIKE %s"
                " OR COALESCE(i.source_metadata->>'title','') ILIKE %s"
                " OR COALESCE(s.accepted_fields->'applicant-name'->>'value','') ILIKE %s)"
            )
            params.extend([needle] * 5)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        try:
            with psycopg.connect(DATABASE_URL) as db:
                total = db.execute("SELECT count(*) FROM (" + CASE_LIST_SQL + where + ") AS matched", params).fetchone()[0]
                rows = db.execute(CASE_LIST_SQL + where + " ORDER BY cs.updated_at DESC,cs.case_id LIMIT %s OFFSET %s", params + [size, start]).fetchall()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"total": total, "limit": size, "offset": start, "cases": [case_list_item(row) for row in rows]}

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
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
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

    @app.get("/cases/{case_id}/routing")
    def routing(case_id: str, request: Request):
        """Read-only, current-revision F-05 status without notification content."""
        if not _authorized(request):
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            with psycopg.connect(DATABASE_URL) as db:
                state = db.execute("SELECT revision FROM current_validation_states WHERE case_id=%s", (case,)).fetchone()
                if not state:
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                route = db.execute("SELECT routing_id,routing_status,route_kind,target_department_id,target_department_label,target_unit_id,target_unit_label FROM routing_operations WHERE case_id=%s AND source_case_revision=%s", (case, state[0])).fetchone()
                if not route:
                    return {"case_id": case_id, "case_revision": state[0], "routing_status": "not_routed", "result": None}
                notifications = db.execute("SELECT audience,generation_status,error_code FROM notification_records WHERE routing_id=%s ORDER BY audience", (route[0],)).fetchall()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {
            "case_id": case_id, "case_revision": state[0], "routing_id": str(route[0]), "routing_status": route[1], "route_kind": route[2],
            "target_department": {"id": route[3], "label": route[4]}, "target_unit": {"id": route[5], "label": route[6]},
            "notifications": [{"audience": item[0], "generation_status": item[1], "error_code": item[2]} for item in notifications],
        }

    @app.get("/cases/{case_id}/document")
    def case_document(case_id: str, request: Request):
        """The citizen's own petition text, as F-01 ingested it.

        Every automatic decision on a case -- the unit it went to, the fields
        that were extracted, the ones reported missing -- was read out of this
        text.  An operator who cannot see it can only take the classifier's word
        for it, so the panel reads it here rather than from whatever the
        submitting browser happened to keep in local storage.

        ADMIN-only for the same reason the queue is: the text is written by the
        applicant and names them.
        """
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        if role != "ADMIN":
            return nested_error(403, "FORBIDDEN", "ADMIN authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            with psycopg.connect(DATABASE_URL) as db:
                record = db.execute(
                    "SELECT document_id,source_type,original_text,language,source_metadata,created_at"
                    " FROM intake_records WHERE case_id=%s",
                    (case,),
                ).fetchone()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        if not record:
            return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
        return case_document_item(case_id, record)

    @app.get("/cases/{case_id}")
    def case_status(case_id: str, request: Request):
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            with psycopg.connect(DATABASE_URL) as db:
                state = db.execute("SELECT revision,state,completed_steps,last_error_code,updated_at FROM current_case_states WHERE case_id=%s", (case,)).fetchone()
                if not state:
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                notices = db.execute("SELECT kind,payload,created_at FROM case_notifications WHERE case_id=%s AND source_case_revision=%s ORDER BY created_at", (case, state[0])).fetchall()
                validation = db.execute("SELECT completion_status FROM current_validation_states WHERE case_id=%s", (case,)).fetchone()
                route_status = db.execute("SELECT routing_status FROM routing_operations WHERE case_id=%s AND source_case_revision=%s", (case, state[0])).fetchone()
                response = {"case_id": case_id, "case_revision": state[0], "state": state[1], "completed_steps": state[2], "last_error_code": state[3], "updated_at": state[4].isoformat(), "validation_status": validation[0] if validation else None, "routing_status": route_status[0] if route_status else "not_routed", "applicant_notifications": [{"kind": row[0], "payload": row[1], "created_at": row[2].isoformat()} for row in notices]}
                if role == "ADMIN":
                    details = db.execute("SELECT s.accepted_fields,c.department_id,c.unit_id,c.request_type_id,g.document_summary,g.draft_text FROM current_validation_states s JOIN current_classifications c USING(document_id) LEFT JOIN correspondence_generations g ON g.generation_id=s.current_correspondence_generation_id WHERE s.case_id=%s", (case,)).fetchone()
                    route = db.execute("SELECT target_department_id,target_unit_id FROM routing_operations WHERE case_id=%s AND source_case_revision=%s", (case, state[0])).fetchone()
                    unit_notice = db.execute("SELECT payload FROM notification_records n JOIN routing_operations r USING(routing_id) WHERE r.case_id=%s AND r.source_case_revision=%s AND n.audience='target_unit'", (case, state[0])).fetchone()
                    if details:
                        response["operational_context"] = {"validated_fields": details[0], "department_id": details[1], "unit_id": details[2], "request_type_id": details[3], "document_summary": details[4], "draft_text": details[5]}
                    response["routing"] = None if not route else {"target_department_id": route[0], "target_unit_id": route[1]}
                    response["target_unit_notification"] = None if not unit_notice else unit_notice[0]
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return response

    @app.post("/cases/{case_id}/review-completion")
    async def complete_review(case_id: str, request: Request):
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        if role != "ADMIN":
            return nested_error(403, "FORBIDDEN", "ADMIN authorization is required")
        try:
            case = uuid.UUID(case_id)
        except ValueError:
            return nested_error(400, "CASE_ID_INVALID", "case_id must be a UUID")
        key, revision, bad = _headers(request)
        if bad:
            return bad
        if await request.body():
            return nested_error(400, "REQUEST_BODY_INVALID", "Body must be empty")
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                cur.execute("SELECT source_case_revision,response_body FROM review_completion_replays WHERE case_id=%s AND idempotency_key=%s FOR UPDATE", (case, key))
                replay = cur.fetchone()
                if replay:
                    if replay[0] != revision:
                        return nested_error(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key was used for another case revision")
                    return replay[1]
                cur.execute("SELECT state FROM current_case_states WHERE case_id=%s AND revision=%s FOR UPDATE", (case, revision))
                row = cur.fetchone()
                if not row:
                    return nested_error(412, "CASE_REVISION_CONFLICT", "If-Match does not match current case revision")
                if row[0] != "needs_review":
                    return nested_error(409, "CASE_NOT_REVIEWABLE", "Only needs_review cases can be completed")
                response = {"case_id": case_id, "case_revision": revision, "state": "completed"}
                cur.execute("UPDATE current_case_states SET state='completed',last_error_code=NULL,updated_at=now() WHERE case_id=%s", (case,))
                cur.execute("INSERT INTO review_completion_replays (case_id,idempotency_key,source_case_revision,response_body) VALUES (%s,%s,%s,%s)", (case, key, revision, Jsonb(response)))
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return response

    return app


app = create_app()
