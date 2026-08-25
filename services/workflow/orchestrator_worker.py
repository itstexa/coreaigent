"""F-06 durable state projection and automatic F-04 starter."""

from __future__ import annotations

import os
import time
import uuid

import psycopg
from psycopg.types.json import Jsonb

from app import CORPUS_VERSION, PROMPT_SCHEMA_VERSION, ensure_schema
from orchestrator import MAX_F04_START_ATTEMPTS, derive_case_state, next_start_action


DATABASE_URL = os.environ["DATABASE_URL"]
LEASE_SECONDS = int(os.environ.get("WORKER_LEASE_SECONDS", "180"))
COOLDOWN_SECONDS = int(os.environ.get("F04_RETRY_COOLDOWN_SECONDS", "30"))
POLL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "0.2"))


def _upsert_state(cur, case_id, revision, state, steps, error=None):
    cur.execute(
        "INSERT INTO current_case_states (case_id,revision,state,completed_steps,last_error_code) VALUES (%s,%s,%s,%s,%s) "
        "ON CONFLICT (case_id) DO UPDATE SET revision=EXCLUDED.revision,"
        "state=CASE WHEN current_case_states.state='completed' AND current_case_states.revision=EXCLUDED.revision THEN 'completed' ELSE EXCLUDED.state END,"
        "completed_steps=EXCLUDED.completed_steps,"
        "last_error_code=CASE WHEN current_case_states.state='completed' AND current_case_states.revision=EXCLUDED.revision THEN NULL ELSE EXCLUDED.last_error_code END,updated_at=now()",
        (case_id, revision, state, Jsonb(steps), error),
    )


def reconcile_once():
    """Project current source rows and enqueue exactly one F-04 start per revision."""
    try:
        with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
            cur.execute(
                "SELECT c.case_id,COALESCE(s.revision,1),s.completion_status,s.missing_fields,s.invalid_fields,c.status,"
                "g.generation_status,g.result_status,r.routing_status,j.attempt_count "
                "FROM current_classifications c LEFT JOIN current_validation_states s USING(document_id) "
                "LEFT JOIN correspondence_generations g ON g.generation_id=s.current_correspondence_generation_id "
                "LEFT JOIN routing_operations r ON r.case_id=s.case_id AND r.source_case_revision=s.revision "
                "LEFT JOIN correspondence_start_jobs j ON j.case_id=s.case_id AND j.source_case_revision=s.revision "
                "ORDER BY c.updated_at LIMIT 100 FOR UPDATE OF c"
            )
            for row in cur.fetchall():
                case_id, revision, completion, missing, invalid, classification, generation, result, route, attempts = row
                notices = {}
                if route == "routed":
                    current = cur.execute("SELECT audience,generation_status FROM notification_records n JOIN routing_operations r USING(routing_id) WHERE r.case_id=%s AND r.source_case_revision=%s", (case_id, revision)).fetchall()
                    notices = dict(current)
                state = derive_case_state(classification, completion, generation, result, route, notices)
                # A failed attempt is still retriable until the approved fourth
                # total try is exhausted.  It must not surface as terminal first.
                terminal = generation == "failed" and (attempts or 0) >= MAX_F04_START_ATTEMPTS
                if generation == "failed" and not terminal:
                    state = "ready_for_processing"
                steps = ["F-01", "F-02"] + (["F-03"] if completion == "complete" else []) + (["F-04"] if generation == "completed" else []) + (["F-05"] if route == "routed" else [])
                _upsert_state(cur, case_id, revision, state, steps, "F04_TERMINAL_FAILURE" if terminal else None)
                if completion in {"missing_information", "invalid_information"}:
                    kind, fields = completion, missing if completion == "missing_information" else invalid
                    cur.execute("INSERT INTO case_notifications (notification_id,case_id,source_case_revision,audience,kind,payload) VALUES (%s,%s,%s,'applicant',%s,%s) ON CONFLICT (case_id,source_case_revision,audience,kind) DO NOTHING", (uuid.uuid4(), case_id, revision, kind, Jsonb({"kind": kind, "fields": fields, "email_placeholder": None})))
                if classification == "classified" and completion == "complete" and generation is None:
                    cur.execute("INSERT INTO correspondence_start_jobs (job_id,case_id,source_case_revision,state,next_attempt_at) VALUES (%s,%s,%s,'pending',now()) ON CONFLICT (case_id,source_case_revision) DO NOTHING", (uuid.uuid4(), case_id, revision))
                if generation == "completed":
                    cur.execute("UPDATE correspondence_start_jobs SET state='completed',claimed_until=NULL,updated_at=now() WHERE case_id=%s AND source_case_revision=%s AND state IN ('pending','claimed','waiting')", (case_id, revision))
                elif generation == "failed":
                    cur.execute("UPDATE correspondence_start_jobs SET state=CASE WHEN attempt_count < %s THEN 'pending' ELSE 'failed' END,next_attempt_at=CASE WHEN attempt_count < %s THEN now()+(%s*interval '1 second') ELSE NULL END,error_code=CASE WHEN attempt_count < %s THEN NULL ELSE 'F04_TERMINAL_FAILURE' END,claimed_until=NULL,updated_at=now() WHERE case_id=%s AND source_case_revision=%s AND state='waiting'", (MAX_F04_START_ATTEMPTS, MAX_F04_START_ATTEMPTS, COOLDOWN_SECONDS, MAX_F04_START_ATTEMPTS, case_id, revision))
    except psycopg.Error:
        return False
    return True


def _claim_start():
    with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
        cur.execute("SELECT job_id,case_id,source_case_revision,attempt_count FROM correspondence_start_jobs WHERE (state='pending' AND next_attempt_at <= now()) OR (state='claimed' AND claimed_until < now()) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1")
        job = cur.fetchone()
        if not job:
            return None
        cur.execute("UPDATE correspondence_start_jobs SET state='claimed',attempt_count=attempt_count+1,claimed_until=now()+(%s*interval '1 second'),updated_at=now() WHERE job_id=%s", (LEASE_SECONDS, job[0]))
        return job


def run_start_once():
    job = _claim_start()
    if not job:
        return False
    try:
        with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
            cur.execute("SELECT s.document_id,s.workflow_id,s.request_type_id,s.completion_status,s.revision,c.status,c.department_label,c.unit_label,s.accepted_fields,s.current_correspondence_generation_id FROM current_validation_states s JOIN current_classifications c USING(document_id) WHERE s.case_id=%s FOR UPDATE OF s,c", (job[1],))
            state = cur.fetchone()
            if not state or state[4] != job[2] or state[3] != "complete" or state[5] != "classified":
                cur.execute("UPDATE correspondence_start_jobs SET state='failed',error_code='CASE_NOT_READY',claimed_until=NULL,updated_at=now() WHERE job_id=%s", (job[0],))
                return True
            generation_status = None
            if state[9]:
                generation_status = cur.execute("SELECT generation_status FROM correspondence_generations WHERE generation_id=%s", (state[9],)).fetchone()[0]
            # job[3] is the count before this claim; the pure decision retains
            # that convention so attempt 0 creates the initial generation.
            if next_start_action(state[5], state[3], generation_status, job[3]) not in {"start", "retry"}:
                cur.execute("UPDATE correspondence_start_jobs SET state='waiting',claimed_until=NULL,updated_at=now() WHERE job_id=%s", (job[0],))
                return True
            generation, generation_job = uuid.uuid4(), uuid.uuid4()
            cur.execute("INSERT INTO correspondence_generations (generation_id,case_id,document_id,workflow_id,source_case_revision,request_type_id,department_label,unit_label,corpus_version,retrieval_config_version,prompt_schema_version,validated_fields,generation_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'municipality-rag-v1',%s,%s,'queued')", (generation, job[1], state[0], state[1], job[2], state[2], state[6], state[7], CORPUS_VERSION, PROMPT_SCHEMA_VERSION, Jsonb(state[8])))
            cur.execute("INSERT INTO correspondence_generation_jobs (job_id,generation_id,state) VALUES (%s,%s,'pending')", (generation_job, generation))
            cur.execute("UPDATE current_validation_states SET current_correspondence_generation_id=%s WHERE case_id=%s AND revision=%s", (generation, job[1], job[2]))
            cur.execute("UPDATE correspondence_start_jobs SET state='waiting',claimed_until=NULL,updated_at=now() WHERE job_id=%s", (job[0],))
    except psycopg.Error:
        with psycopg.connect(DATABASE_URL) as db:
            db.execute("UPDATE correspondence_start_jobs SET state='pending',claimed_until=NULL,next_attempt_at=now()+(%s*interval '1 second'),updated_at=now() WHERE job_id=%s AND state='claimed'", (COOLDOWN_SECONDS, job[0]))
    return True


if __name__ == "__main__":
    ensure_schema()
    while True:
        progressed = run_start_once()
        reconcile_once()
        if not progressed:
            time.sleep(POLL_SECONDS)
