"""PostgreSQL durable outbox worker for F-02 classification."""

import os
import time

import psycopg

from app import classify_document, load_taxonomy


DATABASE_URL = os.environ["DATABASE_URL"]
POLL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "0.2"))
LEASE_SECONDS = int(os.environ.get("WORKER_LEASE_SECONDS", "30"))
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
CREATE TABLE IF NOT EXISTS current_classifications (
    document_id text PRIMARY KEY REFERENCES intake_records(document_id),
    case_id uuid NOT NULL,
    workflow_id uuid NOT NULL,
    status text NOT NULL CHECK (status IN ('classified', 'needs_review')),
    department_id text NULL, department_label text NULL,
    unit_id text NULL, unit_label text NULL,
    request_type_id text NULL, request_type_label text NULL,
    confidence numeric(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    taxonomy_version text NOT NULL, classifier_version text NOT NULL,
    classification_reason text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((department_id IS NULL AND department_label IS NULL AND unit_id IS NULL AND unit_label IS NULL AND request_type_id IS NULL AND request_type_label IS NULL) OR (department_id IS NOT NULL AND department_label IS NOT NULL AND unit_id IS NOT NULL AND unit_label IS NOT NULL AND request_type_id IS NOT NULL AND request_type_label IS NOT NULL)),
    CHECK (status <> 'classified' OR (confidence > 0.80 AND department_id IS NOT NULL))
);
"""


def ensure_schema():
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(SCHEMA_SQL)


def claim():
    with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cursor:
        cursor.execute(
            "SELECT j.job_id, r.document_id, r.case_id, r.workflow_id, r.normalized_text "
            "FROM durable_outbox_jobs j JOIN intake_records r USING (document_id) "
            "WHERE j.kind = 'process_document' AND (j.state = 'pending' OR (j.state = 'claimed' AND j.claimed_until < now())) "
            "ORDER BY j.created_at FOR UPDATE SKIP LOCKED LIMIT 1"
        )
        job = cursor.fetchone()
        if not job:
            return None
        cursor.execute(
            "UPDATE durable_outbox_jobs SET state = 'claimed', attempt_count = attempt_count + 1, claimed_until = now() + (%s * interval '1 second'), updated_at = now() WHERE job_id = %s",
            (LEASE_SECONDS, job[0]),
        )
        return job


def complete(job, classified, taxonomy):
    # The HTTP endpoint and this worker must agree on the scoring model: the
    # browser reads the response, the panel reads the row this writes, and a
    # case whose two halves disagree is unexplainable to an operator.
    result, classifier_version, reason = classified
    department, unit, request_type = result["department"], result["unit"], result["requestType"]
    with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cursor:
        cursor.execute(
            "INSERT INTO current_classifications (document_id, case_id, workflow_id, status, department_id, department_label, unit_id, unit_label, request_type_id, request_type_label, confidence, taxonomy_version, classifier_version, classification_reason) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (document_id) DO UPDATE SET case_id = EXCLUDED.case_id, workflow_id = EXCLUDED.workflow_id, status = EXCLUDED.status, department_id = EXCLUDED.department_id, department_label = EXCLUDED.department_label, unit_id = EXCLUDED.unit_id, unit_label = EXCLUDED.unit_label, request_type_id = EXCLUDED.request_type_id, request_type_label = EXCLUDED.request_type_label, confidence = EXCLUDED.confidence, taxonomy_version = EXCLUDED.taxonomy_version, classifier_version = EXCLUDED.classifier_version, classification_reason = EXCLUDED.classification_reason, updated_at = now()",
            (job[1], job[2], job[3], result["status"], department and department["id"], department and department["label"], unit and unit["id"], unit and unit["label"], request_type and request_type["id"], request_type and request_type["label"], result["confidence"], taxonomy.version, classifier_version, reason),
        )
        cursor.execute("UPDATE durable_outbox_jobs SET state = 'completed', claimed_until = NULL, updated_at = now() WHERE job_id = %s AND state = 'claimed'", (job[0],))


def run_once(taxonomy):
    job = claim()
    if not job:
        return False
    try:
        complete(job, classify_document(job[4], taxonomy), taxonomy)
    except Exception:
        with psycopg.connect(DATABASE_URL) as db, db.transaction():
            db.execute("UPDATE durable_outbox_jobs SET state = 'pending', claimed_until = NULL, updated_at = now() WHERE job_id = %s AND state = 'claimed'", (job[0],))
        raise
    return True


def main():
    ensure_schema()
    taxonomy = load_taxonomy()
    while True:
        if not run_once(taxonomy):
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
