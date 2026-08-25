"""PostgreSQL-durable F-05 routing and local Jamba notification worker."""

from __future__ import annotations

import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from app import ensure_schema
from correspondence import extract_json_object
from routing import RoutingRejected, normalize_notification_output, notification_payload, select_route


DATABASE_URL = os.environ["DATABASE_URL"]
LLM_URL = os.environ.get("JAMBA_URL", "http://llm:8080/generate")
LEASE_SECONDS = int(os.environ.get("WORKER_LEASE_SECONDS", "180"))
POLL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "0.2"))
TAXONOMY_PATH = Path(os.environ.get("TAXONOMY_PATH", Path(__file__).parents[1] / "classification" / "taxonomy.json"))


def taxonomy():
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def _invoke(prompt):
    request = urllib.request.Request(LLM_URL, data=json.dumps({"prompt": prompt}, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=185) as response:
        return json.load(response)


def _claim(table, columns):
    with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
        cur.execute(f"SELECT {columns} FROM {table} WHERE state='pending' OR (state='claimed' AND claimed_until < now()) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1")
        job = cur.fetchone()
        if not job:
            return None
        cur.execute(f"UPDATE {table} SET state='claimed',attempt_count=attempt_count+1,claimed_until=now()+(%s*interval '1 second'),updated_at=now() WHERE job_id=%s", (LEASE_SECONDS, job[0]))
        return job


def _complete_job(table, job_id, *, state="completed", rejection_code=None):
    with psycopg.connect(DATABASE_URL) as db:
        db.execute(f"UPDATE {table} SET state=%s,claimed_until=NULL,rejection_code=%s,updated_at=now() WHERE job_id=%s", (state, rejection_code, job_id))


def _route_job():
    return _claim("routing_jobs", "job_id,case_id,source_case_revision,source_generation_id,recovery_reason")


def _notification_job():
    return _claim("notification_jobs", "job_id,notification_id")


def _route_state(cur, job):
    cur.execute(
        "SELECT s.revision,s.completion_status,s.request_type_id,c.status,c.department_id,c.unit_id,"
        "g.generation_status,g.result_status,g.source_status "
        "FROM current_validation_states s JOIN current_classifications c USING(document_id) "
        "LEFT JOIN correspondence_generations g ON g.generation_id=%s WHERE s.case_id=%s FOR UPDATE OF s,c",
        (job[3], job[1]),
    )
    return cur.fetchone()


def _create_route(job):
    with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
        row = _route_state(cur, job)
        if not row or row[0] != job[2]:
            raise RoutingRejected("CASE_REVISION_CONFLICT")
        if job[3] and (row[6] != "completed" or row[7] not in {"draft_ready", "review_required"}):
            raise RoutingRejected("CORRESPONDENCE_NOT_ROUTEABLE")
        result_status = row[7] if job[3] else "not_requested"
        route = select_route(taxonomy(), classification_status=row[3], completion_status=row[1], result_status=result_status, department_id=row[4], unit_id=row[5])
        departments = {item["id"]: item for item in taxonomy()["departments"]}
        units = {item["id"]: item for item in taxonomy()["units"]}
        routing_id = uuid.uuid4()
        cur.execute(
            "INSERT INTO routing_operations (routing_id,case_id,source_case_revision,source_generation_id,request_type_id,route_kind,target_department_id,target_department_label,target_unit_id,target_unit_label,taxonomy_version,routing_status,routing_reason,routed_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'routed',%s,now()) ON CONFLICT (case_id,source_case_revision) DO NOTHING RETURNING routing_id",
            (routing_id, job[1], job[2], job[3], row[2], route["route_kind"], route["department_id"], departments[route["department_id"]]["label"], route["unit_id"], units[route["unit_id"]]["label"], route["taxonomy_version"], Jsonb({"source_status": row[8], "recovery_reason": job[4]})),
        )
        inserted = cur.fetchone()
        if not inserted:
            return None
        for audience in ("applicant", "target_unit"):
            notification_id, notification_job_id = uuid.uuid4(), uuid.uuid4()
            cur.execute("INSERT INTO notification_records (notification_id,routing_id,audience,generation_status) VALUES (%s,%s,%s,'queued')", (notification_id, routing_id, audience))
            cur.execute("INSERT INTO notification_jobs (job_id,notification_id,state) VALUES (%s,%s,'pending')", (notification_job_id, notification_id))
        return routing_id


def run_route_once():
    job = _route_job()
    if not job:
        return False
    try:
        _create_route(job)
    except RoutingRejected as exc:
        _complete_job("routing_jobs", job[0], state="rejected", rejection_code=str(exc))
    except Exception:
        # Leave transient infrastructure/model-independent failures durable.
        with psycopg.connect(DATABASE_URL) as db:
            db.execute("UPDATE routing_jobs SET state='pending',claimed_until=NULL,updated_at=now() WHERE job_id=%s AND state='claimed'", (job[0],))
    else:
        _complete_job("routing_jobs", job[0])
    return True


def _notification_context(cur, notification_id):
    cur.execute(
        "SELECT n.audience,r.case_id,r.request_type_id,g.document_summary,g.draft_text,g.regulation_suggestions,s.accepted_fields "
        "FROM notification_records n JOIN routing_operations r USING(routing_id) "
        "LEFT JOIN correspondence_generations g ON g.generation_id=r.source_generation_id "
        "JOIN current_validation_states s ON s.case_id=r.case_id AND s.revision=r.source_case_revision WHERE n.notification_id=%s FOR UPDATE OF n,r,s",
        (notification_id,),
    )
    return cur.fetchone()


def _notification_prompt(audience, context, repair_error=None):
    if audience == "applicant":
        input_context = {"instruction": "Başvurunun işleme alındığını, ilgili birime yönlendirildiğini ve inceleme sonucunun bildirileceğini söyle."}
    else:
        input_context = {
            "request_type_id": context[2], "document_summary": context[3], "draft_text": context[4],
            "regulation_suggestions": context[5], "validated_fields": context[6],
        }
    repair_rule = " Önceki çıktı reddedildi: " + repair_error + ". Sadece title ve body anahtarlarını döndür." if repair_error else ""
    return (
        "Türkçe kısa belediye bildirimi üret. Yalnız tek JSON object döndür; markdown veya başka anahtar yok. "
        "body en fazla iki kısa cümle ve 600 karakter olsun. JSON nesnesini mutlaka kapat ve nesneden sonra yazmayı durdur. "
        "Zorunlu şema: title(string), body(string). body boş olamaz. Alıcı: " + audience + ". "
        + ("Başvuru sahibi için iç metadata, alan değerleri, taslak veya birim adı verme. " if audience == "applicant" else "Hedef birim için yalnız verilen case bağlamını kullan; yeni olgu uydurma. ")
        + "Örnek: {\"title\":\"Başvuru işleme alındı\",\"body\":\"Başvurunuz ilgili birime yönlendirilmiştir.\"}."
        + repair_rule + "\nGirdi:\n"
        + json.dumps(input_context, ensure_ascii=False)
    )


def _validate_notification(raw, audience):
    payload = extract_json_object(raw)
    return normalize_notification_output(payload)


def run_notification_once():
    job = _notification_job()
    if not job:
        return False
    try:
        with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
            cur.execute("UPDATE notification_records SET generation_status='processing' WHERE notification_id=%s AND generation_status='queued'", (job[1],))
            context = _notification_context(cur, job[1])
        if not context:
            raise ValueError("NOTIFICATION_CONTEXT_NOT_FOUND")
        repair_error = None
        for attempt in (1, 2):
            try:
                model = _invoke(_notification_prompt(context[0], context, repair_error))
                generated = _validate_notification(model["response"], context[0])
                payload = notification_payload(context[0], str(context[1]), generated["body"], {
                    "request_type_id": context[2], "document_summary": context[3], "draft_text": context[4], "regulation_suggestions": context[5], "validated_fields": context[6],
                })
                payload["title"] = generated["title"].strip()
                with psycopg.connect(DATABASE_URL) as db:
                    db.execute("UPDATE notification_records SET generation_status='completed',payload=%s,model_id=%s,model_revision=%s,attempt_count=%s,completed_at=now(),error_code=NULL WHERE notification_id=%s AND generation_status='processing'", (Jsonb(payload), model.get("model"), model.get("modelRevision"), attempt, job[1]))
                _complete_job("notification_jobs", job[0])
                return True
            except Exception as exc:
                repair_error = str(exc) or "STRUCTURED_OUTPUT_INVALID"
        with psycopg.connect(DATABASE_URL) as db:
            db.execute("UPDATE notification_records SET generation_status='failed',payload=NULL,attempt_count=2,error_code='STRUCTURED_OUTPUT_INVALID',completed_at=now() WHERE notification_id=%s AND generation_status='processing'", (job[1],))
        _complete_job("notification_jobs", job[0])
        return True
    except Exception:
        with psycopg.connect(DATABASE_URL) as db:
            db.execute("UPDATE notification_jobs SET state='pending',claimed_until=NULL,updated_at=now() WHERE job_id=%s AND state='claimed'", (job[0],))
        return True


def recover_once():
    """Queue overlooked complete current cases, but never failed/in-progress F-04 work."""
    try:
        with psycopg.connect(DATABASE_URL) as db, db.transaction(), db.cursor() as cur:
            cur.execute(
            "SELECT s.case_id,s.revision,s.current_correspondence_generation_id FROM current_validation_states s "
            "JOIN current_classifications c USING(document_id) "
            "LEFT JOIN correspondence_generations g ON g.generation_id=s.current_correspondence_generation_id "
            "LEFT JOIN routing_operations r ON r.case_id=s.case_id AND r.source_case_revision=s.revision "
            "WHERE s.completion_status='complete' AND c.status='classified' AND r.routing_id IS NULL "
            "AND (s.current_correspondence_generation_id IS NULL OR g.generation_status='completed') "
            "ORDER BY s.updated_at LIMIT 25 FOR UPDATE SKIP LOCKED"
            )
            rows = cur.fetchall()
            for case_id, revision, generation_id in rows:
                cur.execute(
                "INSERT INTO routing_jobs (job_id,case_id,source_case_revision,source_generation_id,recovery_reason,state) VALUES (%s,%s,%s,%s,'reconciliation','pending') "
                "ON CONFLICT (case_id,source_case_revision) DO NOTHING",
                    (uuid.uuid4(), case_id, revision, generation_id),
                )
    except psycopg.Error:
        # Validation owns these source tables and can legitimately be starting
        # at the same time.  A later scan repairs this without treating it as a
        # terminal routing rejection.
        return False
    return bool(rows)


if __name__ == "__main__":
    ensure_schema()
    while True:
        progressed = run_route_once() or run_notification_once()
        if not progressed:
            recover_once()
            time.sleep(POLL_SECONDS)
