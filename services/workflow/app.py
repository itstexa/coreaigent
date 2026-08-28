"""F-04 case-level correspondence API backed by PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb

from correspondence import RETRIEVAL_CONFIG_VERSION, sanitize_learning_fields, sanitize_text
from assignment import behavior_signals

DATABASE_URL = os.environ.get("DATABASE_URL", "")
AUTH_TOKEN = os.environ.get("CASE_ACCESS_TOKEN", "")
ADMIN_TOKEN = os.environ.get("CASE_ADMIN_TOKEN", "")
CORPUS_VERSION = "demo-municipality-regulations-v2"
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
CREATE TABLE IF NOT EXISTS staff_members (
 staff_id text PRIMARY KEY, display_name text NOT NULL, role text NOT NULL CHECK (role IN ('operator','moderator','admin')),
 unit_id text NOT NULL, active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS case_assignments (
 assignment_id uuid PRIMARY KEY, case_id uuid NOT NULL, source_case_revision bigint NOT NULL CHECK (source_case_revision > 0),
 unit_id text NOT NULL, request_type_id text NULL, staff_id text NULL REFERENCES staff_members(staff_id), display_name text NULL, role text NULL,
 selection_reason jsonb NOT NULL DEFAULT '{}'::jsonb,
 assignment_status text NOT NULL CHECK (assignment_status IN ('assigned','unassigned','completed')),
 assigned_at timestamptz NULL, completed_at timestamptz NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (case_id, source_case_revision)
);
ALTER TABLE case_assignments ADD COLUMN IF NOT EXISTS request_type_id text NULL;
ALTER TABLE case_assignments ADD COLUMN IF NOT EXISTS selection_reason jsonb NOT NULL DEFAULT '{}'::jsonb;
DO $$ BEGIN
 IF to_regclass('public.current_validation_states') IS NOT NULL THEN
  UPDATE case_assignments a
  SET request_type_id = s.request_type_id
  FROM current_validation_states s
  WHERE a.request_type_id IS NULL
    AND a.case_id = s.case_id
    AND a.source_case_revision = s.revision;
 END IF;
END $$;
INSERT INTO staff_members (staff_id,display_name,role,unit_id) VALUES
 ('beyaz-masa-operator-1','Beyaz Masa Operatörü 1','operator','beyaz-masa'),
 ('beyaz-masa-operator-2','Beyaz Masa Operatörü 2','moderator','beyaz-masa'),
 ('dijital-hizmetler-operator-1','Dijital Hizmetler Operatörü 1','operator','dijital-hizmetler'),
 ('dijital-hizmetler-operator-2','Dijital Hizmetler Operatörü 2','moderator','dijital-hizmetler'),
 ('gelir-tahakkuk-operator-1','Gelir ve Tahakkuk Operatörü 1','operator','gelir-tahakkuk'),
 ('gelir-tahakkuk-operator-2','Gelir ve Tahakkuk Operatörü 2','moderator','gelir-tahakkuk'),
 ('ruhsat-operator-1','Ruhsat Operatörü 1','operator','ruhsat'),
 ('ruhsat-operator-2','Ruhsat Operatörü 2','moderator','ruhsat'),
 ('denetim-operator-1','Denetim Operatörü 1','operator','denetim'),
 ('denetim-operator-2','Denetim Operatörü 2','moderator','denetim'),
 ('siniflandirilmamis-operator-1','Genel Başvuru Operatörü 1','operator','siniflandirilmamis'),
 ('siniflandirilmamis-operator-2','Genel Başvuru Operatörü 2','moderator','siniflandirilmamis')
 ON CONFLICT (staff_id) DO NOTHING;
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
 priority_level text NOT NULL DEFAULT 'normal' CHECK (priority_level IN ('critical','high','normal')),
 priority_score smallint NOT NULL DEFAULT 40 CHECK (priority_score IN (40,70,100)), priority_reason text NOT NULL DEFAULT 'Öncelik sinyali bulunmadı',
 updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE current_case_states ADD COLUMN IF NOT EXISTS priority_level text NOT NULL DEFAULT 'normal';
ALTER TABLE current_case_states ADD COLUMN IF NOT EXISTS priority_score smallint NOT NULL DEFAULT 40;
ALTER TABLE current_case_states ADD COLUMN IF NOT EXISTS priority_reason text NOT NULL DEFAULT 'Öncelik sinyali bulunmadı';
CREATE TABLE IF NOT EXISTS case_tickets (
 case_id uuid PRIMARY KEY, ticket_reference text NOT NULL UNIQUE,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (ticket_reference ~ '^CA-[0-9A-F]{8}$')
);
CREATE TABLE IF NOT EXISTS case_action_log (
 action_id bigserial PRIMARY KEY, case_id uuid NOT NULL REFERENCES case_tickets(case_id),
 action_type text NOT NULL CHECK (action_type='state_projected'),
 actor text NOT NULL CHECK (actor='system'), facts jsonb NOT NULL DEFAULT '{}'::jsonb,
 occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS case_action_log_case_time_idx ON case_action_log(case_id, action_id);
CREATE OR REPLACE FUNCTION case_action_log_is_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'case_action_log is immutable'; END $$;
DROP TRIGGER IF EXISTS case_action_log_no_mutation ON case_action_log;
CREATE TRIGGER case_action_log_no_mutation BEFORE UPDATE OR DELETE ON case_action_log
 FOR EACH ROW EXECUTE FUNCTION case_action_log_is_immutable();
INSERT INTO case_tickets (case_id,ticket_reference)
 SELECT case_id,'CA-' || upper(substr(replace(case_id::text,'-',''),1,8)) FROM current_case_states
 ON CONFLICT (case_id) DO NOTHING;
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
CREATE TABLE IF NOT EXISTS learning_feedback (
 feedback_id uuid PRIMARY KEY, case_id uuid NOT NULL, source_case_revision bigint NOT NULL CHECK (source_case_revision > 0),
 document_id text NOT NULL, request_type_id text NOT NULL, sanitized_text text NOT NULL,
 validated_fields jsonb NOT NULL DEFAULT '{}'::jsonb, status text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','exported')),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (case_id, source_case_revision)
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


def ticket_reference(case_id):
    """Stable local ticket label; it is not an external helpdesk identifier."""
    return "CA-" + str(case_id).replace("-", "")[:8].upper()


def action_log_item(row):
    """Project only the allowlisted, non-PII facts of an immutable F0 action."""
    action_id, action_type, actor, facts, occurred_at = row
    if action_type != "state_projected":
        raise ValueError("unrecognised action type")
    values = facts if isinstance(facts, dict) else {}
    revision = values.get("revision")
    return {
        "action_id": action_id,
        "type": action_type,
        "actor": actor,
        "state": values.get("state") if isinstance(values.get("state"), str) else None,
        "case_revision": revision if isinstance(revision, int) and revision > 0 else None,
        "completed_steps": values.get("completed_steps") if isinstance(values.get("completed_steps"), list) and all(isinstance(step, str) for step in values["completed_steps"]) else [],
        "last_error_code": values.get("last_error_code") if isinstance(values.get("last_error_code"), str) else None,
        "occurred_at": occurred_at.isoformat(),
    }


# The applicant is named by whichever field the request type's schema defines
# for it; the admin list shows one column, so the first present key wins.
APPLICANT_NAME_KEYS = ("applicant-name", "business-name", "supplier-name")
CASE_LIST_MAX_LIMIT = 100
RELATED_CASE_LIMIT = 5
RELATED_CASE_THRESHOLD = 20


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


def _fold_text(value):
    return (value or "").lower().translate(str.maketrans("ığüşöç", "igusoc"))


def applicant_identity(accepted_fields):
    """A local comparison key, never returned to a caller."""
    value = _applicant_name(accepted_fields)
    return " ".join(_fold_text(value).split()) if value else None


def text_similarity_score(reference, candidate):
    """Deterministic token overlap for F3 history; no model or raw-text response."""
    left = set(re.findall(r"[a-z0-9]{3,}", _fold_text(reference)))
    right = set(re.findall(r"[a-z0-9]{3,}", _fold_text(candidate)))
    return 0 if not left or not right else round(100 * len(left & right) / len(left | right))


def related_case_item(row, score):
    case_id, document_id, state, created_at, source_metadata = row
    return {
        "case_id": str(case_id), "document_id": document_id, "state": state,
        "resolved": state == "completed", "submitted_at": created_at.isoformat(),
        "similarity_score": score, "title": _metadata_text(source_metadata, "title"),
    }


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
    (case_id, revision, state, completed_steps, last_error_code, priority_level, priority_score, priority_reason, updated_at, completion_status,
     document_id, request_type_id, accepted_fields, department_id, department_label, unit_id,
     unit_label, request_type_label, classification_status, confidence, routing_status,
     created_at, language, source_metadata, classification_reason) = row
    return {
        "case_id": str(case_id),
        "case_revision": revision,
        "state": state,
        "completed_steps": completed_steps or [],
        "last_error_code": last_error_code,
        "priority": {"level": priority_level, "score": priority_score, "reason": priority_reason},
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
    "SELECT cs.case_id,cs.revision,cs.state,cs.completed_steps,cs.last_error_code,cs.priority_level,cs.priority_score,cs.priority_reason,cs.updated_at,"
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
                rows = db.execute(CASE_LIST_SQL + where + " ORDER BY cs.priority_score DESC,cs.updated_at DESC,cs.case_id LIMIT %s OFFSET %s", params + [size, start]).fetchall()
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
                cur.execute("INSERT INTO correspondence_generations (generation_id,case_id,document_id,workflow_id,source_case_revision,request_type_id,department_label,unit_label,corpus_version,retrieval_config_version,prompt_schema_version,validated_fields,generation_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued')", (generation, case, state[0], state[1], expected_revision, state[2], state[5], state[6], CORPUS_VERSION, RETRIEVAL_CONFIG_VERSION, PROMPT_SCHEMA_VERSION, Jsonb(state[7])))
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

    @app.get("/cases/{case_id}/related-cases")
    def related_cases(case_id: str, request: Request):
        """ADMIN-only, bounded same-applicant history without returning petition bodies."""
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
                current = db.execute(
                    "SELECT i.original_text,s.accepted_fields FROM intake_records i "
                    "LEFT JOIN current_validation_states s ON s.case_id=i.case_id WHERE i.case_id=%s", (case,),
                ).fetchone()
                if not current:
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                identity = applicant_identity(current[1])
                if not identity:
                    return {"case_id": case_id, "history_scope": "unavailable", "similar_count": 0, "related_cases": []}
                rows = db.execute(
                    "SELECT cs.case_id,i.document_id,cs.state,i.created_at,i.source_metadata,i.original_text,s.accepted_fields "
                    "FROM current_case_states cs JOIN intake_records i ON i.case_id=cs.case_id "
                    "LEFT JOIN current_validation_states s ON s.case_id=cs.case_id "
                    "WHERE cs.case_id<>%s ORDER BY i.created_at DESC LIMIT 200", (case,),
                ).fetchall()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        matched = []
        for candidate in rows:
            if applicant_identity(candidate[6]) != identity:
                continue
            score = text_similarity_score(current[0], candidate[5])
            if score >= RELATED_CASE_THRESHOLD:
                matched.append((candidate, score))
        matched.sort(key=lambda item: (-item[1], item[0][3], str(item[0][0])))
        return {
            "case_id": case_id, "history_scope": "same_validated_applicant", "similar_count": len(matched),
            "related_cases": [related_case_item(item[:5], score) for item, score in matched[:RELATED_CASE_LIMIT]],
        }

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
                    details = db.execute("SELECT s.accepted_fields,c.department_id,c.unit_id,c.request_type_id,g.document_summary,g.draft_text,i.normalized_text,i.language FROM current_validation_states s JOIN current_classifications c USING(document_id) JOIN intake_records i USING(document_id) LEFT JOIN correspondence_generations g ON g.generation_id=s.current_correspondence_generation_id WHERE s.case_id=%s", (case,)).fetchone()
                    route = db.execute("SELECT target_department_id,target_unit_id FROM routing_operations WHERE case_id=%s AND source_case_revision=%s", (case, state[0])).fetchone()
                    unit_notice = db.execute("SELECT payload FROM notification_records n JOIN routing_operations r USING(routing_id) WHERE r.case_id=%s AND r.source_case_revision=%s AND n.audience='target_unit'", (case, state[0])).fetchone()
                    if details:
                        response["operational_context"] = {"validated_fields": details[0], "department_id": details[1], "unit_id": details[2], "request_type_id": details[3], "document_summary": details[4], "draft_text": details[5]}
                        response["behavior_signal"] = behavior_signals(details[6], source_language=details[7])
                    response["routing"] = None if not route else {"target_department_id": route[0], "target_unit_id": route[1]}
                    response["target_unit_notification"] = None if not unit_notice else unit_notice[0]
                    assignment = db.execute(
                        "SELECT a.assignment_status,a.unit_id,a.staff_id,a.display_name,a.role,"
                        "(SELECT COUNT(*) FROM case_assignments open_a WHERE open_a.staff_id=a.staff_id AND open_a.assignment_status='assigned'),a.selection_reason "
                        "FROM case_assignments a WHERE a.case_id=%s AND a.source_case_revision=%s",
                        (case, state[0]),
                    ).fetchone()
                    response["assignment"] = None if not assignment else {
                        "status": assignment[0], "unit_id": assignment[1], "staff_id": assignment[2],
                        "display_name": assignment[3], "role": assignment[4], "open_assignment_count": assignment[5] or 0,
                        "selection_reason": assignment[6] or {},
                    }
                    # The assignment policy has the authoritative bounded
                    # history counts (same applicant/topic) used for F2. Keep
                    # the visible behavior card consistent with that decision
                    # instead of showing a fresh-text-only repeat count.
                    if response.get("behavior_signal") and assignment and isinstance(assignment[6], dict):
                        for key in ("repeat_count", "marker_count", "aggression_level", "aggression_score", "priority_mode"):
                            if key in assignment[6]:
                                response["behavior_signal"][key] = assignment[6][key]
                    ticket = db.execute("SELECT ticket_reference,created_at FROM case_tickets WHERE case_id=%s", (case,)).fetchone()
                    actions = db.execute("SELECT action_id,action_type,actor,facts,occurred_at FROM case_action_log WHERE case_id=%s ORDER BY action_id", (case,)).fetchall()
                    # A pre-F0 case can have a ticket backfilled during schema
                    # setup but no invented historical action rows.
                    response["ticket"] = {"reference": ticket[0], "created_at": ticket[1].isoformat()} if ticket else None
                    response["action_log"] = [action_log_item(row) for row in actions]
                    feedback = db.execute("SELECT feedback_id,status,created_at FROM learning_feedback WHERE case_id=%s AND source_case_revision=%s", (case, state[0])).fetchone()
                    response["learning_feedback"] = None if not feedback else {"feedback_id": str(feedback[0]), "status": feedback[1], "created_at": feedback[2].isoformat()}
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return response

    @app.post("/cases/{case_id}/learning-feedback")
    async def create_learning_feedback(case_id: str, request: Request):
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        if role != "ADMIN":
            return nested_error(403, "FORBIDDEN", "ADMIN authorization is required")
        try:
            case = uuid.UUID(case_id)
        except ValueError:
            return nested_error(400, "CASE_ID_INVALID", "case_id must be a UUID")
        _key, revision, bad = _headers(request)
        if bad:
            return bad
        if await request.body():
            return nested_error(400, "REQUEST_BODY_INVALID", "Body must be empty")
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                cur.execute("SELECT feedback_id,status,created_at FROM learning_feedback WHERE case_id=%s AND source_case_revision=%s", (case, revision))
                existing = cur.fetchone()
                if existing:
                    return {"case_id": case_id, "case_revision": revision, "feedback_id": str(existing[0]), "status": existing[1], "created_at": existing[2].isoformat()}
                cur.execute(
                    "SELECT cs.state,s.revision,s.completion_status,s.accepted_fields,s.request_type_id,i.document_id,i.normalized_text "
                    "FROM current_case_states cs JOIN current_validation_states s USING(case_id) JOIN intake_records i USING(document_id) "
                    "WHERE cs.case_id=%s AND cs.revision=%s FOR UPDATE OF cs,s",
                    (case, revision),
                )
                row = cur.fetchone()
                if not row:
                    return nested_error(412, "CASE_REVISION_CONFLICT", "If-Match does not match current case revision")
                if row[0] != "completed" or row[2] != "complete":
                    return nested_error(409, "CASE_NOT_READY_FOR_LEARNING", "Only a completed case with complete validation can become a learning candidate")
                policy = json.loads(Path(__file__).with_name("f04_pii_policy.json").read_text(encoding="utf-8"))
                fields = row[3] or {}
                known = {key: value["value"] for key, value in fields.items() if policy["fieldHandling"].get(key) == "redact" and isinstance(value, dict) and isinstance(value.get("value"), str)}
                sanitized = sanitize_text(row[6], known_values=known, field_handling=policy["fieldHandling"])[:12000]
                candidate_fields = sanitize_learning_fields(fields, field_handling=policy["fieldHandling"])
                feedback_id = uuid.uuid4()
                cur.execute(
                    "INSERT INTO learning_feedback (feedback_id,case_id,source_case_revision,document_id,request_type_id,sanitized_text,validated_fields) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING created_at",
                    (feedback_id, case, revision, row[5], row[4], sanitized, Jsonb(candidate_fields)),
                )
                created_at = cur.fetchone()[0]
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"case_id": case_id, "case_revision": revision, "feedback_id": str(feedback_id), "status": "candidate", "created_at": created_at.isoformat()}

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
