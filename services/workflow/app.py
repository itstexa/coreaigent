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

try:  # script entrypoint in the image; package import in unit tests
    from action_log import append_action_log
except ImportError:  # pragma: no cover - depends on the launch mode
    from services.workflow.action_log import append_action_log
try:
    from dlp import DlpError, redact_text
except ImportError:  # pragma: no cover - depends on the launch mode
    from services.workflow.dlp import DlpError, redact_text
try:
    from similarity import similar_case
except ImportError:  # pragma: no cover - depends on the launch mode
    from services.workflow.similarity import similar_case
try:
    from abuse import analyze_submission
except ImportError:  # pragma: no cover
    from services.workflow.abuse import analyze_submission
try:
    from attachments import AttachmentError, load_required_rules, missing_required_types, relation, similarity_suggestion, validate_metadata
except ImportError:  # pragma: no cover - depends on the launch mode
    from services.workflow.attachments import AttachmentError, load_required_rules, missing_required_types, relation, similarity_suggestion, validate_metadata
try:
    from priority import apply_override, calculate_priority
except ImportError:  # pragma: no cover
    from services.workflow.priority import apply_override, calculate_priority
try:
    from normalizer import suggest
except ImportError:  # pragma: no cover
    from services.workflow.normalizer import suggest
try:
    from revisions import edit_decision, next_revision, validate_edit
except ImportError:
    from services.workflow.revisions import edit_decision, next_revision, validate_edit
try:
    from draft import make_draft
except ImportError:
    from services.workflow.draft import make_draft
try:
    from routing import evaluate_routing, ROUTING_CONFIDENCE_THRESHOLD
except ImportError:  # pragma: no cover
    from services.workflow.routing import evaluate_routing, ROUTING_CONFIDENCE_THRESHOLD

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
CREATE TABLE IF NOT EXISTS routing_feedback (
 feedback_id uuid PRIMARY KEY, case_id uuid NOT NULL REFERENCES current_case_states(case_id),
 source_case_revision bigint NOT NULL CHECK (source_case_revision > 0), predicted_unit_id text NOT NULL,
 accepted_unit_id text NOT NULL, confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
 routing_correct boolean NOT NULL, actor text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (case_id, source_case_revision)
);
CREATE INDEX IF NOT EXISTS routing_feedback_unit_idx ON routing_feedback (accepted_unit_id, created_at);
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
CREATE TABLE IF NOT EXISTS case_revisions (
 case_id uuid NOT NULL REFERENCES current_case_states(case_id), revision bigint NOT NULL CHECK (revision > 0), parent_revision bigint NULL,
 document_id text NOT NULL, actor_id text NOT NULL CHECK (length(trim(actor_id)) > 0), payload jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(),
 change_kind text NOT NULL CHECK (change_kind IN ('initial','petition_edit')), PRIMARY KEY (case_id, revision), UNIQUE (document_id)
);
CREATE TABLE IF NOT EXISTS case_action_logs (
 event_id uuid PRIMARY KEY, case_id uuid NOT NULL REFERENCES current_case_states(case_id),
 action_type text NOT NULL CHECK (action_type IN ('state_change','assignment','petition_edit','attachment_change','spam_decision','view','download')),
 actor text NOT NULL CHECK (length(trim(actor)) > 0), occurred_at timestamptz NOT NULL DEFAULT now(),
 details jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS case_action_logs_case_time_idx ON case_action_logs (case_id, occurred_at, event_id);
CREATE TABLE IF NOT EXISTS case_abuse_assessments (
 case_id uuid PRIMARY KEY REFERENCES current_case_states(case_id),
 label text NOT NULL CHECK (label IN ('clear','review')),
 confidence numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
 risk_score numeric NOT NULL CHECK (risk_score >= 0 AND risk_score <= 1),
 flagged boolean NOT NULL,
 detected_signals jsonb NOT NULL DEFAULT '[]'::jsonb,
 override_flagged boolean NULL,
 override_reason text NULL,
 analyzed_at timestamptz NOT NULL DEFAULT now(),
 override_at timestamptz NULL,
 CHECK (override_flagged IS NULL OR (override_reason IS NOT NULL AND length(trim(override_reason)) > 0))
);
CREATE TABLE IF NOT EXISTS case_priorities (
 case_id uuid PRIMARY KEY REFERENCES current_case_states(case_id), level text NOT NULL CHECK (level IN ('low','normal','high','urgent')),
 policy_version text NOT NULL, reason text NOT NULL, override_reason text NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS unit_personnel (
 person_id text PRIMARY KEY, unit_id text NOT NULL, display_name text NOT NULL CHECK (length(trim(display_name)) > 0)
);
CREATE TABLE IF NOT EXISTS case_assignments (
 assignment_id uuid PRIMARY KEY, case_id uuid NOT NULL REFERENCES current_case_states(case_id),
 source_case_revision bigint NOT NULL CHECK (source_case_revision > 0), person_id text NOT NULL REFERENCES unit_personnel(person_id),
 assigned_at timestamptz NOT NULL DEFAULT now(), UNIQUE (case_id, source_case_revision)
);
CREATE TABLE IF NOT EXISTS case_resolution_marks (
 case_id uuid NOT NULL REFERENCES current_case_states(case_id), actor text NOT NULL,
 marked_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (case_id, actor)
);
CREATE TABLE IF NOT EXISTS case_attachments (
 attachment_id uuid PRIMARY KEY, case_id uuid NOT NULL REFERENCES current_case_states(case_id),
 attachment_type text NOT NULL CHECK (length(trim(attachment_type)) > 0), filename text NOT NULL,
 content_type text NOT NULL, size_bytes bigint NOT NULL CHECK (size_bytes >= 0), storage_key text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS case_attachments_case_idx ON case_attachments (case_id, created_at, attachment_id);
CREATE TABLE IF NOT EXISTS case_attachment_relations (
 relation_id uuid PRIMARY KEY, case_id uuid NOT NULL REFERENCES current_case_states(case_id),
 source_attachment_id uuid NOT NULL REFERENCES case_attachments(attachment_id),
 target_attachment_id uuid NOT NULL REFERENCES case_attachments(attachment_id),
 method text NOT NULL CHECK (method IN ('manual','rule','similarity_suggestion')),
 authoritative boolean NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((method='similarity_suggestion' AND authoritative=false) OR (method IN ('manual','rule') AND authoritative=true)),
 UNIQUE (source_attachment_id,target_attachment_id,method)
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


def attachment_item(row):
    """Project attachment metadata without exposing the object-store key."""
    attachment_id, attachment_type, filename, content_type, size_bytes, created_at = row
    return {
        "attachment_id": str(attachment_id),
        "attachment_type": attachment_type,
        "filename": filename,
        "content_type": content_type,
        "size_bytes": int(size_bytes),
        "created_at": created_at.isoformat(),
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

    @app.post("/v1/normalize")
    async def normalize_text(request: Request):
        try:
            body = await request.json()
            if not isinstance(body, dict): raise ValueError
            return suggest(body.get("text"), body.get("language", "tr"))
        except (ValueError, TypeError, json.JSONDecodeError):
            return JSONResponse(status_code=422, content={"error": "invalid_text"})

    @app.post("/v1/drafts")
    async def citizen_draft(request: Request):
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("invalid_request")
            return make_draft(payload.get("document_type"), payload.get("fields"), payload.get("text", ""))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return JSONResponse(status_code=422, content={"error": str(exc) or "invalid_request"})

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

    @app.get("/personnel-dashboard")
    def personnel_dashboard(request: Request):
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        if role != "ADMIN":
            return nested_error(403, "FORBIDDEN", "ADMIN authorization is required")
        scope = request.query_params.get("scope", "system")
        try: period = int(request.query_params.get("period_days", "30"))
        except ValueError: period = -1
        unit_id = request.query_params.get("unit_id")
        if scope not in {"unit", "system"} or period not in {7, 30, 90} or (scope == "unit" and not unit_id):
            return nested_error(400, "QUERY_INVALID", "scope must be unit or system, period_days must be 7, 30, or 90, and unit_id is required for unit scope")
        filt = " AND p.unit_id=%s" if scope == "unit" else ""
        args = [unit_id] if scope == "unit" else []
        try:
            with psycopg.connect(DATABASE_URL) as db:
                active = db.execute("SELECT count(*) FROM unit_personnel p WHERE 1=1" + filt, args).fetchone()[0]
                open_count = db.execute("SELECT count(*) FROM case_assignments a JOIN unit_personnel p USING(person_id) JOIN current_case_states s USING(case_id) WHERE s.state NOT IN ('completed','failed')" + filt, args).fetchone()[0]
                completed = db.execute("SELECT count(*) FROM case_revisions r JOIN current_case_states s USING(case_id) JOIN case_assignments a USING(case_id) JOIN unit_personnel p USING(person_id) WHERE s.state='completed' AND r.created_at >= now()-(%s || ' days')::interval" + filt, [period] + args).fetchone()[0]
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"scope": scope, "unit_id": unit_id if scope == "unit" else None, "period_days": period, "metrics": {"active_personnel": active, "open_assignments": open_count, "completed_cases": completed, "throughput": completed / period, "average_resolution_hours": None}}

    @app.get("/moderation-trends")
    def moderation_trends(request: Request):
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        scope = request.query_params.get("scope", "system")
        try:
            period_days = int(request.query_params.get("period_days", "30"))
        except ValueError:
            period_days = -1
        if scope not in {"user", "unit", "system"} or period_days not in {7, 30, 90}:
            return nested_error(400, "QUERY_INVALID", "scope must be user, unit, or system and period_days must be 7, 30, or 90")
        if scope in {"unit", "system"} and role != "ADMIN":
            return nested_error(403, "FORBIDDEN", "ADMIN authorization is required")
        if scope == "user":
            return {"status": "no_data", "scope": scope, "period_days": period_days, "points": []}
        try:
            with psycopg.connect(DATABASE_URL) as db:
                if scope == "unit":
                    rows = db.execute("SELECT date_trunc('day',a.analyzed_at)::date,c.unit_id,count(*),count(*) FILTER (WHERE a.flagged) FROM case_abuse_assessments a JOIN current_classifications c USING(case_id) WHERE a.analyzed_at >= now() - (%s || ' days')::interval GROUP BY 1,c.unit_id HAVING count(*) >= 5 ORDER BY 1,c.unit_id", (period_days,)).fetchall()
                else:
                    rows = db.execute("SELECT date_trunc('day',analyzed_at)::date,'system',count(*),count(*) FILTER (WHERE flagged) FROM case_abuse_assessments WHERE analyzed_at >= now() - (%s || ' days')::interval GROUP BY 1 HAVING count(*) >= 5 ORDER BY 1", (period_days,)).fetchall()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        points = [{"bucket": row[0].isoformat(), "key": row[1], "total": row[2], "flagged": row[3], "rate": row[3] / row[2]} for row in rows]
        return {"status": "data" if points else "no_data", "scope": scope, "period_days": period_days, "points": points}

    @app.get("/cases/{case_id}/priority")
    def case_priority(case_id: str, request: Request):
        if not _role(request): return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad: return bad
        try:
            with psycopg.connect(DATABASE_URL) as db:
                row = db.execute("SELECT level,policy_version,reason,override_reason,updated_at FROM case_priorities WHERE case_id=%s", (case,)).fetchone()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        if not row: return {"case_id": case_id, "level": "normal", "policy_version": "priority-policy-v1", "reason": "no qualifying urgency signal; default priority", "override_reason": None, "updated_at": None}
        return {"case_id": case_id, "level": row[0], "policy_version": row[1], "reason": row[2], "override_reason": row[3], "updated_at": row[4].isoformat()}

    @app.post("/cases/{case_id}/priority-override")
    async def priority_override(case_id: str, request: Request):
        if _role(request) != "ADMIN": return nested_error(403, "FORBIDDEN", "ADMIN authorization is required")
        case, bad = _case_uuid(case_id)
        if bad: return bad
        try:
            body = await request.json()
            if not isinstance(body, dict) or set(body) != {"level", "reason"}: raise ValueError
            result = apply_override({"level": body["level"]}, body["level"], body["reason"])
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return nested_error(422, "PRIORITY_OVERRIDE_INVALID", "level and non-empty reason are required")
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                if not cur.execute("SELECT 1 FROM current_case_states WHERE case_id=%s", (case,)).fetchone(): return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                cur.execute("INSERT INTO case_priorities(case_id,level,policy_version,reason,override_reason) VALUES (%s,%s,'priority-policy-v1','human override',%s) ON CONFLICT (case_id) DO UPDATE SET level=EXCLUDED.level,override_reason=EXCLUDED.override_reason,reason=EXCLUDED.reason,updated_at=now()", (case, result["level"], result["override_reason"]))
                append_action_log(cur, case, "state_change", "ADMIN", {"priority": result["level"], "reason": result["override_reason"]})
        except psycopg.Error: return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"case_id": case_id, "level": result["level"], "reason": result["override_reason"], "actor": "ADMIN"}

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
                append_action_log(cur, case, "state_change", "USER", {"state": "correspondence_queued", "case_revision": expected_revision, "job_id": str(job)})
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
                assignee = db.execute("SELECT a.person_id,p.display_name FROM case_assignments a JOIN unit_personnel p USING(person_id) WHERE a.case_id=%s AND a.source_case_revision=%s", (case, state[0])).fetchone()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {
            "case_id": case_id, "case_revision": state[0], "routing_id": str(route[0]), "routing_status": route[1], "route_kind": route[2],
            "target_department": {"id": route[3], "label": route[4]}, "target_unit": {"id": route[5], "label": route[6]},
            "assignee": None if not assignee else {"id": assignee[0], "name": assignee[1]},
            "notifications": [{"audience": item[0], "generation_status": item[1], "error_code": item[2]} for item in notifications],
        }

    @app.get("/cases/{case_id}/routing-evaluation")
    def routing_evaluation(case_id: str, request: Request):
        if not _role(request): return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad: return bad
        try:
            with psycopg.connect(DATABASE_URL) as db:
                row = db.execute("SELECT predicted_unit_id,accepted_unit_id,confidence,routing_correct,source_case_revision,created_at FROM routing_feedback WHERE case_id=%s ORDER BY created_at DESC LIMIT 1", (case,)).fetchone()
        except psycopg.Error: return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        if not row: return {"case_id": case_id, "feedback": None}
        return {"case_id": case_id, "feedback": {"predicted_unit_id": row[0], "accepted_unit_id": row[1], "confidence": float(row[2]), "routing_correct": row[3], "case_revision": row[4], "created_at": row[5].isoformat()}}

    @app.get("/routing-evaluation")
    def routing_evaluation_aggregate(request: Request):
        if _role(request) != "ADMIN": return nested_error(403, "FORBIDDEN", "ADMIN authorization is required")
        try:
            with psycopg.connect(DATABASE_URL) as db:
                rows = db.execute("SELECT COALESCE(accepted_unit_id,'system'),count(*),count(*) FILTER (WHERE routing_correct) FROM routing_feedback GROUP BY 1 ORDER BY 1").fetchall()
        except psycopg.Error: return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"aggregates": [{"unit_id": r[0], "total": r[1], "correct": r[2], "accuracy": r[2] / r[1] if r[1] else 0.0} for r in rows]}

    @app.post("/cases/{case_id}/routing-feedback")
    async def routing_feedback(case_id: str, request: Request):
        if _role(request) != "ADMIN": return nested_error(403, "FORBIDDEN", "ADMIN authorization is required")
        case, bad = _case_uuid(case_id)
        if bad: return bad
        try:
            body = await request.json()
            accepted = body["accepted_unit_id"]
            if not isinstance(accepted, str) or not accepted.strip(): raise ValueError
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return nested_error(400, "FEEDBACK_INVALID", "accepted_unit_id is required")
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                row = cur.execute("SELECT r.target_unit_id,r.source_case_revision,c.confidence FROM routing_operations r JOIN current_classifications c USING(case_id) WHERE r.case_id=%s ORDER BY r.source_case_revision DESC LIMIT 1", (case,)).fetchone()
                if not row: return nested_error(404, "ROUTING_NOT_FOUND", "Routing was not found")
                result = evaluate_routing(row[0], accepted, float(row[2]))
                cur.execute("INSERT INTO routing_feedback(feedback_id,case_id,source_case_revision,predicted_unit_id,accepted_unit_id,confidence,routing_correct,actor) VALUES (%s,%s,%s,%s,%s,%s,%s,'ADMIN') ON CONFLICT (case_id,source_case_revision) DO UPDATE SET accepted_unit_id=EXCLUDED.accepted_unit_id, routing_correct=EXCLUDED.routing_correct", (uuid.uuid4(), case, row[1], row[0], accepted, row[2], result["routing_correct"]))
        except psycopg.Error: return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"case_id": case_id, **result, "training_eligible": False}

    @app.get("/cases/{case_id}/action-log")
    def action_log(case_id: str, request: Request):
        """Return immutable actions for a case to any existing case reader."""
        if not _role(request):
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            with psycopg.connect(DATABASE_URL) as db:
                if not db.execute("SELECT 1 FROM current_case_states WHERE case_id=%s", (case,)).fetchone():
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                rows = db.execute(
                    "SELECT event_id,action_type,actor,occurred_at,details FROM case_action_logs "
                    "WHERE case_id=%s ORDER BY occurred_at,event_id", (case,)
                ).fetchall()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"case_id": case_id, "events": [
            {"event_id": str(row[0]), "action_type": row[1], "actor": row[2],
             "occurred_at": row[3].isoformat(), "details": row[4] or {}}
            for row in rows
        ]}

    @app.get("/cases/{case_id}/abuse")
    def abuse_assessment(case_id: str, request: Request):
        """Return review-only abuse metadata to an authorized moderator."""
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        if role != "ADMIN":
            return nested_error(403, "FORBIDDEN", "Moderator authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            with psycopg.connect(DATABASE_URL) as db:
                if not db.execute("SELECT 1 FROM current_case_states WHERE case_id=%s", (case,)).fetchone():
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                row = db.execute(
                    "SELECT label,confidence,risk_score,flagged,detected_signals,override_flagged,override_reason,analyzed_at,override_at "
                    "FROM case_abuse_assessments WHERE case_id=%s", (case,)
                ).fetchone()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        if not row:
            return nested_error(404, "ABUSE_ASSESSMENT_NOT_FOUND", "Abuse assessment was not found")
        effective = row[5] if row[5] is not None else row[3]
        return {
            "case_id": case_id, "label": "review" if effective else "clear",
            "confidence": float(row[1]), "risk_score": float(row[2]), "flagged": bool(row[3]),
            "detected_signals": row[4] or [], "override_flagged": row[5],
            "override_reason": row[6], "effective_flagged": bool(effective),
            "analyzed_at": row[7].isoformat(), "override_at": row[8].isoformat() if row[8] else None,
        }

    @app.post("/cases/{case_id}/abuse-override")
    async def abuse_override(case_id: str, request: Request):
        """Persist a moderator decision and append the BX-00 spam event."""
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        if role != "ADMIN":
            return nested_error(403, "FORBIDDEN", "Moderator authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return nested_error(400, "REQUEST_BODY_INVALID", "Body must contain flagged and reason")
        if not isinstance(body, dict) or set(body) != {"flagged", "reason"} or not isinstance(body["flagged"], bool):
            return nested_error(400, "REQUEST_BODY_INVALID", "Body must contain boolean flagged and reason")
        reason = body["reason"]
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            return nested_error(422, "OVERRIDE_REASON_REQUIRED", "A non-empty override reason is required")
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                cur.execute("SELECT 1 FROM current_case_states WHERE case_id=%s", (case,))
                if not cur.fetchone():
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                cur.execute("SELECT analyzed_at FROM case_abuse_assessments WHERE case_id=%s FOR UPDATE", (case,))
                row = cur.fetchone()
                if not row:
                    return nested_error(404, "ABUSE_ASSESSMENT_NOT_FOUND", "Abuse assessment was not found")
                cur.execute(
                    "UPDATE case_abuse_assessments SET override_flagged=%s,override_reason=%s,override_at=now() WHERE case_id=%s "
                    "RETURNING override_at", (body["flagged"], reason.strip(), case)
                )
                marked_at = cur.fetchone()[0]
                append_action_log(cur, case, "spam_decision", role, {
                    "override_flagged": body["flagged"], "reason": reason.strip(),
                })
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"case_id": case_id, "override_flagged": body["flagged"], "reason": reason.strip(), "actor": role, "overridden_at": marked_at.isoformat()}

    @app.get("/cases/{case_id}/training-export")
    def training_export(case_id: str, request: Request):
        """Return one irreversibly redacted training-data projection."""
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                cur.execute(
                    "SELECT i.document_id,i.normalized_text,COALESCE(s.accepted_fields,'{}'::jsonb) "
                    "FROM current_case_states cs JOIN intake_records i USING(case_id) "
                    "LEFT JOIN current_validation_states s USING(case_id) WHERE cs.case_id=%s",
                    (case,),
                )
                record = cur.fetchone()
                if not record:
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                accepted = record[2] or {}
                names = []
                for field_id, value in accepted.items() if isinstance(accepted, dict) else ():
                    if not isinstance(field_id, str) or not field_id.endswith("-name"):
                        continue
                    value = value.get("value") if isinstance(value, dict) else value
                    if isinstance(value, str) and value.strip():
                        names.append(value)
                projection = redact_text(record[1] or "", names)
                response = {"case_id": case_id, "document_id": record[0], **projection}
                append_action_log(cur, case, "download", role, {
                    "export_type": "training_dataset", "redactions": projection["redactions"],
                })
        except DlpError:
            return nested_error(422, "DLP_REDACTION_FAILED", "Training export could not prove safe redaction")
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return response

    @app.get("/cases/{case_id}/history")
    def case_history(case_id: str, request: Request):
        """Return same-classification cases from the preceding 30 days."""
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                cur.execute(
                    "SELECT cs.state,c.request_type_id,i.created_at,i.normalized_text,i.source_metadata "
                    "FROM current_case_states cs JOIN intake_records i USING(case_id) "
                    "JOIN current_classifications c USING(case_id) WHERE cs.case_id=%s",
                    (case,),
                )
                current = cur.fetchone()
                if not current:
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                cur.execute("SELECT actor,marked_at FROM case_resolution_marks WHERE case_id=%s ORDER BY marked_at,actor", (case,))
                current_marks = cur.fetchall()
                current_metadata = current[4] if isinstance(current[4], dict) else {}
                cur.execute(
                    "SELECT cs.case_id,cs.state,c.request_type_id,i.created_at,i.normalized_text,i.source_metadata "
                    "FROM current_case_states cs JOIN intake_records i USING(case_id) "
                    "JOIN current_classifications c USING(case_id) "
                    "WHERE c.request_type_id=%s AND i.created_at >= %s - interval '30 days' "
                    "AND i.created_at <= %s AND cs.case_id<>%s ORDER BY i.created_at DESC",
                    (current[1], current[2], current[2], case),
                )
                similar_rows = cur.fetchall()
                similar = []
                for row in similar_rows:
                    metadata = row[5] if isinstance(row[5], dict) else {}
                    decision = similar_case(
                        {"created_at": current[2], "classification": current[1], "text": current[3], "location": current_metadata.get("location")},
                        {"created_at": row[3], "classification": row[2], "text": row[4], "location": metadata.get("location")},
                    )
                    cur.execute("SELECT actor,marked_at FROM case_resolution_marks WHERE case_id=%s ORDER BY marked_at,actor", (row[0],))
                    marks = cur.fetchall()
                    viewers = cur.execute("SELECT DISTINCT actor FROM case_action_logs WHERE case_id=%s AND action_type='view' ORDER BY actor", (row[0],)).fetchall()
                    similar.append({
                        "case_id": str(row[0]), "created_at": row[3].isoformat(), "state": row[1],
                        "classification": row[2], "resolved": bool(marks), "resolved_by": [item[0] for item in marks],
                        "viewers": [item[0] for item in viewers], "signals": decision["signals"],
                    })
                append_action_log(cur, case, "view", role, {"view": "history"})
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {
            "case_id": case_id, "resolved": bool(current_marks),
            "resolved_by": [item[0] for item in current_marks], "similar_cases": similar,
        }

    @app.post("/cases/{case_id}/resolution-mark")
    async def resolution_mark(case_id: str, request: Request):
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        raw = await request.body()
        if raw:
            try:
                if json.loads(raw) != {}:
                    return nested_error(400, "REQUEST_BODY_INVALID", "Body must be empty or {}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                return nested_error(400, "REQUEST_BODY_INVALID", "Body must be empty or {}")
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                cur.execute("SELECT 1 FROM current_case_states WHERE case_id=%s", (case,))
                if not cur.fetchone():
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                cur.execute("INSERT INTO case_resolution_marks (case_id,actor) VALUES (%s,%s) ON CONFLICT (case_id,actor) DO NOTHING RETURNING marked_at", (case, role))
                marked = cur.fetchone()
                if not marked:
                    cur.execute("SELECT marked_at FROM case_resolution_marks WHERE case_id=%s AND actor=%s", (case, role))
                    marked = cur.fetchone()
                append_action_log(cur, case, "state_change", role, {"resolution": "marked"}, event_id=uuid.uuid5(uuid.NAMESPACE_URL, f"coreaigent:case:{case}:resolved:{role}"))
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"case_id": case_id, "resolved": True, "actor": role, "marked_at": marked[0].isoformat()}

    @app.get("/cases/{case_id}/attachments")
    def case_attachments(case_id: str, request: Request):
        """Return metadata, required types, and non-authoritative suggestions."""
        if not _role(request):
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            with psycopg.connect(DATABASE_URL) as db:
                state = db.execute(
                    "SELECT cs.state,COALESCE(s.request_type_id,c.request_type_id) "
                    "FROM current_case_states cs LEFT JOIN current_validation_states s USING(case_id) "
                    "LEFT JOIN current_classifications c USING(case_id) WHERE cs.case_id=%s", (case,)
                ).fetchone()
                if not state:
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                rows = db.execute(
                    "SELECT attachment_id,attachment_type,filename,content_type,size_bytes,created_at "
                    "FROM case_attachments WHERE case_id=%s ORDER BY created_at,attachment_id", (case,)
                ).fetchall()
                relation_rows = db.execute(
                    "SELECT source_attachment_id,target_attachment_id,method,authoritative "
                    "FROM case_attachment_relations WHERE case_id=%s ORDER BY created_at,relation_id", (case,)
                ).fetchall()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        attachments = [attachment_item(row) for row in rows]
        rules = load_required_rules()
        missing = missing_required_types(state[1], [row[1] for row in rows], rules)
        suggestions = []
        # The endpoint only suggests pairs; it never inserts them as relations.
        for item in attachments:
            suggestions.extend({"source_attachment_id": item["attachment_id"], **suggestion} for suggestion in similarity_suggestion(item["filename"], [other for other in attachments if other["attachment_id"] != item["attachment_id"]]))
        return {
            "case_id": case_id, "state": state[0], "request_type_id": state[1],
            "missing_required_types": missing, "attachments": attachments,
            "relations": [{"source_attachment_id": str(row[0]), "target_attachment_id": str(row[1]), "method": row[2], "authoritative": row[3]} for row in relation_rows],
            "suggestions": suggestions,
        }

    @app.post("/cases/{case_id}/attachments")
    async def add_case_attachment(case_id: str, request: Request):
        """Register an object-store object and its DB metadata."""
        role = _role(request)
        if not role:
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return nested_error(400, "REQUEST_BODY_INVALID", "Body must be a JSON object")
        required = {"attachment_type", "filename", "content_type", "size_bytes", "storage_key"}
        optional = {"related_attachment_id", "relation_method"}
        if not isinstance(body, dict) or set(body) - required - optional or not required <= set(body):
            return nested_error(400, "REQUEST_BODY_INVALID", "attachment_type, filename, content_type, size_bytes and storage_key are required")
        if not isinstance(body["attachment_type"], str) or not body["attachment_type"].strip() or len(body["attachment_type"]) > 128:
            return nested_error(422, "ATTACHMENT_TYPE_INVALID", "attachment_type must be a non-empty string of at most 128 characters")
        try:
            metadata = validate_metadata(body["filename"], body["content_type"], body["size_bytes"], body["storage_key"])
        except AttachmentError as exc:
            return nested_error(422, exc.code, str(exc))
        attachment_id = uuid.uuid4()
        related_id = body.get("related_attachment_id")
        method = body.get("relation_method", "manual")
        relation_data = None
        related_uuid = None
        if related_id is not None:
            try:
                related_uuid = uuid.UUID(related_id)
                relation_data = relation(method, str(attachment_id), str(related_uuid))
            except (ValueError, TypeError, AttributeError, AttachmentError) as exc:
                return nested_error(422, getattr(exc, "code", "RELATION_INVALID"), str(exc) or "invalid attachment relation")
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                cur.execute("SELECT state,COALESCE(s.request_type_id,c.request_type_id) FROM current_case_states cs LEFT JOIN current_validation_states s USING(case_id) LEFT JOIN current_classifications c USING(case_id) WHERE cs.case_id=%s FOR UPDATE", (case,))
                state = cur.fetchone()
                if not state:
                    return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                if state[0] not in {"draft", "draft_prepared", "waiting_for_information", "waiting_for_user"}:
                    return nested_error(409, "CASE_REVISION_REQUIRED", "Submitted case attachment changes require a BX-05 revision")
                count = cur.execute("SELECT count(*) FROM case_attachments WHERE case_id=%s", (case,)).fetchone()[0]
                if count >= 10:
                    return nested_error(422, "CASE_FILE_LIMIT", "A case may contain at most 10 files")
                if related_uuid is not None:
                    cur.execute("SELECT 1 FROM case_attachments WHERE attachment_id=%s AND case_id=%s", (related_uuid,case))
                    if not cur.fetchone():
                        return nested_error(422, "RELATION_INVALID", "related attachment belongs to another case")
                cur.execute("INSERT INTO case_attachments (attachment_id,case_id,attachment_type,filename,content_type,size_bytes,storage_key) VALUES (%s,%s,%s,%s,%s,%s,%s)", (attachment_id,case,body["attachment_type"],metadata["filename"],metadata["content_type"],metadata["size_bytes"],metadata["storage_key"]))
                if related_uuid is not None:
                    cur.execute("INSERT INTO case_attachment_relations (relation_id,case_id,source_attachment_id,target_attachment_id,method,authoritative) VALUES (%s,%s,%s,%s,%s,%s)", (uuid.uuid4(),case,attachment_id,related_uuid,relation_data["method"],relation_data["authoritative"]))
                append_action_log(cur, case, "attachment_change", role, {"attachment_id": str(attachment_id), "operation": "attach"})
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"case_id": case_id, "attachment": {"attachment_id": str(attachment_id), "attachment_type": body["attachment_type"], "filename": metadata["filename"], "content_type": metadata["content_type"], "size_bytes": metadata["size_bytes"]}}

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

    @app.get("/cases/{case_id}/revisions")
    def case_revisions(case_id: str, request: Request):
        if not _role(request):
            return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad:
            return bad
        try:
            with psycopg.connect(DATABASE_URL) as db:
                rows = db.execute("SELECT revision,parent_revision,document_id,actor_id,created_at,change_kind,payload FROM case_revisions WHERE case_id=%s ORDER BY revision", (case,)).fetchall()
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return {"case_id": case_id, "revisions": [{"revision": row[0], "parent_revision": row[1], "document_id": row[2], "actor": row[3], "created_at": row[4].isoformat(), "change_kind": row[5], "payload": row[6]} for row in rows]}

    @app.patch("/cases/{case_id}/edit")
    async def edit_case(case_id: str, request: Request):
        role = _role(request)
        if not role: return nested_error(401, "UNAUTHORIZED", "Bearer authorization is required")
        case, bad = _case_uuid(case_id)
        if bad: return bad
        _key, expected, bad = _headers(request)
        if bad: return bad
        try: payload = validate_edit(await request.json())
        except (ValueError, json.JSONDecodeError): return nested_error(400, "REQUEST_BODY_INVALID", "Invalid edit payload")
        try:
            with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
                row = cur.execute("SELECT revision,state FROM current_case_states WHERE case_id=%s FOR UPDATE", (case,)).fetchone()
                if not row: return nested_error(404, "CASE_NOT_FOUND", "Case state was not found")
                if row[0] != expected: return nested_error(412, "CASE_REVISION_CONFLICT", "If-Match does not match current case revision")
                if edit_decision(row[1]) == "terminal": return nested_error(409, "CASE_NOT_EDITABLE", "Case cannot be edited in its current state")
                revision = next_revision(row[0]); document_id = f"{case_id}-revision-{revision}"
                cur.execute("INSERT INTO case_revisions(case_id,revision,parent_revision,document_id,actor_id,payload,change_kind) VALUES (%s,%s,%s,%s,%s,%s,'petition_edit')", (case, revision, row[0], document_id, role, Jsonb(payload)))
                cur.execute("UPDATE current_case_states SET revision=%s,updated_at=now() WHERE case_id=%s", (revision, case))
                append_action_log(cur, case, "petition_edit", role, {"case_revision": revision, "parent_revision": row[0]})
                return {"case_id": case_id, "case_revision": revision, "parent_revision": row[0], "document_id": document_id, "state": row[1], "change_kind": "petition_edit"}
        except psycopg.Error: return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")

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
                append_action_log(cur, case, "state_change", "ADMIN", {"state": "completed", "case_revision": revision})
                cur.execute("INSERT INTO review_completion_replays (case_id,idempotency_key,source_case_revision,response_body) VALUES (%s,%s,%s,%s)", (case, key, revision, Jsonb(response)))
        except psycopg.Error:
            return nested_error(503, "POSTGRES_UNAVAILABLE", "PostgreSQL is unavailable")
        return response

    return app


app = create_app()
