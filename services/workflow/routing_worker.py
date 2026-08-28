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
from assignment import behavior_signals, choose_staff, normalize_identity
from orchestrator import MAX_F04_START_ATTEMPTS
from correspondence import extract_json_object
from routing import RoutingRejected, normalize_notification_output, notification_payload, select_route
from translation import TranslationUnavailable, translate


DATABASE_URL = os.environ["DATABASE_URL"]
LLM_URL = os.environ.get("JAMBA_URL", "http://llm:8080/generate")
LLM_TIMEOUT_SECONDS = float(os.environ.get("JAMBA_TIMEOUT_SECONDS", "185") or 185)
LEASE_SECONDS = int(os.environ.get("WORKER_LEASE_SECONDS", "180"))
POLL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "0.2"))
TAXONOMY_PATH = Path(os.environ.get("TAXONOMY_PATH", Path(__file__).parents[1] / "classification" / "taxonomy.json"))


def taxonomy():
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))


def _invoke(prompt):
    request = urllib.request.Request(LLM_URL, data=json.dumps({"prompt": prompt}, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=LLM_TIMEOUT_SECONDS) as response:
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
        _assign_case(cur, job[1], job[2], route["unit_id"], row[2])
        for audience in ("applicant", "target_unit"):
            notification_id, notification_job_id = uuid.uuid4(), uuid.uuid4()
            cur.execute("INSERT INTO notification_records (notification_id,routing_id,audience,generation_status) VALUES (%s,%s,%s,'queued')", (notification_id, routing_id, audience))
            cur.execute("INSERT INTO notification_jobs (job_id,notification_id,state) VALUES (%s,%s,'pending')", (notification_job_id, notification_id))
        return routing_id


def _assign_case(cur, case_id, revision, unit_id, request_type_id):
    """Persist one current-revision assignment after the route is durable."""
    cur.execute(
        "SELECT assignment_id FROM case_assignments WHERE case_id=%s AND source_case_revision=%s",
        (case_id, revision),
    )
    if cur.fetchone():
        return
    # Serialize choices for one unit without locking unrelated municipal work.
    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (unit_id,))
    cur.execute(
        "SELECT s.accepted_fields,i.normalized_text,i.language FROM current_validation_states s "
        "JOIN intake_records i USING(document_id) WHERE s.case_id=%s AND s.revision=%s",
        (case_id, revision),
    )
    context = cur.fetchone() or ({}, "", "unknown")
    identity = normalize_identity(context[0])
    previous_topic_count = 0
    if identity:
        cur.execute(
            "SELECT s.accepted_fields,c.request_type_id FROM current_validation_states s "
            "JOIN current_classifications c USING(document_id) WHERE s.case_id<>%s",
            (case_id,),
        )
        previous_topic_count = sum(
            1 for fields, topic in cur.fetchall()
            if topic == request_type_id and normalize_identity(fields) == identity
        )
    signals = behavior_signals(context[1], previous_topic_count=previous_topic_count, same_topic=bool(identity), source_language=context[2])
    cur.execute(
        "SELECT s.staff_id,s.display_name,s.role,COUNT(a.assignment_id) FILTER (WHERE a.assignment_status='assigned')::int,MAX(a.assigned_at), "
        "COUNT(a.assignment_id) FILTER (WHERE a.request_type_id=%s)::int, "
        "COUNT(a.assignment_id) FILTER (WHERE a.request_type_id=%s AND a.assignment_status='completed')::int "
        "FROM staff_members s LEFT JOIN case_assignments a "
        "ON a.staff_id=s.staff_id "
        "WHERE s.unit_id=%s AND s.active=true "
        "GROUP BY s.staff_id,s.display_name,s.role "
        "ORDER BY COUNT(a.assignment_id) FILTER (WHERE a.assignment_status='assigned'),MAX(a.assigned_at) NULLS FIRST,s.staff_id LIMIT 25",
        (request_type_id, request_type_id, unit_id),
    )
    candidates = [
        {
            "staff_id": row[0], "display_name": row[1], "role": row[2], "open_count": row[3],
            "last_assigned_at": row[4], "topic_total": row[5], "topic_resolved": row[6],
            "resolution_rate": (row[6] / row[5]) if row[5] else 0.0,
        }
        for row in cur.fetchall()
    ]
    selected = choose_staff(candidates, prioritize_resolution=signals["priority_mode"])
    policy = "topic_resolution_rate" if signals["priority_mode"] and any(c["topic_total"] for c in candidates) else "least_open_assignments"
    selection_reason = {
        "policy": policy,
        "repeat_count": signals["repeat_count"],
        "aggression_level": signals["aggression_level"],
        "aggression_score": signals["aggression_score"],
        "marker_count": signals["marker_count"],
        "topic_request_type_id": request_type_id,
        "staff_topic_cases": selected["topic_total"] if selected else 0,
        "staff_topic_resolution_rate": round(selected["resolution_rate"], 3) if selected else 0.0,
    }
    if not selected:
        cur.execute(
            "INSERT INTO case_assignments (assignment_id,case_id,source_case_revision,unit_id,request_type_id,selection_reason,assignment_status) "
            "VALUES (%s,%s,%s,%s,%s,%s,'unassigned') ON CONFLICT (case_id,source_case_revision) DO NOTHING",
            (uuid.uuid4(), case_id, revision, unit_id, request_type_id, Jsonb(selection_reason)),
        )
        return
    cur.execute(
        "SELECT state FROM current_case_states WHERE case_id=%s AND revision=%s",
        (case_id, revision),
    )
    assignment_status = "completed" if (cur.fetchone() or [None])[0] == "completed" else "assigned"
    cur.execute(
        "INSERT INTO case_assignments (assignment_id,case_id,source_case_revision,unit_id,request_type_id,staff_id,display_name,role,selection_reason,assignment_status,assigned_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()) ON CONFLICT (case_id,source_case_revision) DO NOTHING",
        (uuid.uuid4(), case_id, revision, unit_id, request_type_id, selected["staff_id"], selected["display_name"], selected["role"], Jsonb(selection_reason), assignment_status),
    )


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
        "SELECT n.audience,r.case_id,r.request_type_id,g.document_summary,g.draft_text,g.regulation_suggestions,s.accepted_fields,i.language "
        "FROM notification_records n JOIN routing_operations r USING(routing_id) "
        "LEFT JOIN correspondence_generations g ON g.generation_id=r.source_generation_id "
        "JOIN current_validation_states s ON s.case_id=r.case_id AND s.revision=r.source_case_revision "
        "JOIN intake_records i ON i.document_id=s.document_id WHERE n.notification_id=%s FOR UPDATE OF n,r,s",
        (notification_id,),
    )
    return cur.fetchone()


# The applicant reads their own notification, so it follows the language of the
# document they filed.  The target unit's notification always stays in the
# authority's own language: it is read by municipal staff, not by the applicant,
# and the case context it quotes is stored in Turkish either way.
NOTIFICATION_INSTRUCTIONS = {
    "tr": {
        "header": (
            "Türkçe kısa belediye bildirimi üret. Yalnız tek JSON object döndür; markdown veya başka anahtar yok. "
            "body en fazla iki kısa cümle ve 600 karakter olsun. JSON nesnesini mutlaka kapat ve nesneden sonra yazmayı durdur. "
            "Zorunlu şema: title(string), body(string). body boş olamaz. Alıcı: {audience}. "
        ),
        "applicant_rule": "Başvuru sahibi için iç metadata, alan değerleri, taslak veya birim adı verme. ",
        "target_rule": "Hedef birim için yalnız verilen case bağlamını kullan; yeni olgu uydurma. ",
        "example": "Örnek: {\"title\":\"Başvuru işleme alındı\",\"body\":\"Başvurunuz ilgili birime yönlendirilmiştir.\"}.",
        "repair": " Önceki çıktı reddedildi: {error}. Sadece title ve body anahtarlarını döndür.",
        "input": "\nGirdi:\n",
        "applicant_instruction": "Başvurunun işleme alındığını, ilgili birime yönlendirildiğini ve inceleme sonucunun bildirileceğini söyle.",
    },
    "en": {
        "header": (
            "Produce a short English municipal notification. Return exactly one JSON object; no markdown and no other keys. "
            "body must be at most two short sentences and 600 characters. Close the JSON object and stop writing after it. "
            "Required schema: title(string), body(string). body must not be empty. Recipient: {audience}. "
        ),
        "applicant_rule": "For the applicant, disclose no internal metadata, field values, draft text or unit name. ",
        "target_rule": "For the target unit, use only the case context provided; invent no new facts. ",
        "example": "Example: {\"title\":\"Your application has been received\",\"body\":\"Your application has been forwarded to the relevant unit.\"}.",
        "repair": " The previous output was rejected: {error}. Return only the title and body keys.",
        "input": "\nInput:\n",
        "applicant_instruction": "State that the application has been received, forwarded to the relevant unit, and that the outcome of the review will be communicated.",
    },
}
NOTIFICATION_FALLBACK_LANGUAGE = "tr"


def notification_language(audience, language):
    """Resolve the language one notification is written in.

    Only the applicant's copy follows the document; anything unrecognised -- an
    "unknown" detection included -- falls back to the authority's own language.
    """
    if audience != "applicant" or language not in NOTIFICATION_INSTRUCTIONS:
        return NOTIFICATION_FALLBACK_LANGUAGE
    return language


def _notification_prompt(audience, context, repair_error=None, language=None):
    wording = NOTIFICATION_INSTRUCTIONS[notification_language(audience, language)]
    if audience == "applicant":
        input_context = {"instruction": wording["applicant_instruction"]}
    else:
        input_context = {
            "request_type_id": context[2], "document_summary": context[3], "draft_text": context[4],
            "regulation_suggestions": context[5], "validated_fields": context[6],
        }
    repair_rule = wording["repair"].format(error=repair_error) if repair_error else ""
    return (
        wording["header"].format(audience=audience)
        + (wording["applicant_rule"] if audience == "applicant" else wording["target_rule"])
        + wording["example"] + repair_rule + wording["input"]
        + json.dumps(input_context, ensure_ascii=False)
    )


def _validate_notification(raw, audience):
    payload = extract_json_object(raw)
    return normalize_notification_output(payload)


def _english_notification_context(audience, context, language):
    if language != "tr":
        return context
    translated = list(context)
    # F-05's free-text context fields are natural language; identifiers and
    # validated-field keys remain untouched.
    for index in (3, 4):
        if isinstance(translated[index], str):
            translated[index] = translate(translated[index], "tr", "en")
    return tuple(translated)


def _applicant_notification_language(output, language):
    if language != "tr":
        return output
    return {key: translate(value, "en", "tr") if isinstance(value, str) else value for key, value in output.items()}


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
                prompt_context = _english_notification_context(context[0], context, context[7])
                model = _invoke(_notification_prompt(context[0], prompt_context, repair_error, "en" if context[7] == "tr" else context[7]))
                generated = _validate_notification(model["response"], context[0])
                generated = _applicant_notification_language(generated, context[7])
                payload = notification_payload(context[0], str(context[1]), generated["body"], {
                    "request_type_id": context[2], "document_summary": context[3], "draft_text": context[4], "regulation_suggestions": context[5], "validated_fields": context[6],
                })
                payload["title"] = generated["title"].strip()
                with psycopg.connect(DATABASE_URL) as db:
                    db.execute("UPDATE notification_records SET generation_status='completed',payload=%s,model_id=%s,model_revision=%s,attempt_count=%s,completed_at=now(),error_code=NULL WHERE notification_id=%s AND generation_status='processing'", (Jsonb(payload), model.get("model"), model.get("modelRevision"), attempt, job[1]))
                _complete_job("notification_jobs", job[0])
                return True
            except TranslationUnavailable:
                raise
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
            # A case with no generation is not necessarily overlooked: the
            # orchestrator enqueues the F-04 start on the same poll validation
            # completes, so reconciling that window routed every fresh case to
            # the fallback unit as `not_requested` and the real `draft_ready`
            # route was then dropped by the routing_jobs conflict clause.  Only
            # a case F-04 has given up on is genuinely awaiting a fallback.
            "AND (g.generation_status='completed' OR (s.current_correspondence_generation_id IS NULL AND EXISTS ("
            " SELECT 1 FROM correspondence_start_jobs j WHERE j.case_id=s.case_id AND j.source_case_revision=s.revision"
            " AND (j.state='failed' OR (j.state='waiting' AND j.attempt_count >= %s))))) "
            "ORDER BY s.updated_at LIMIT 25 FOR UPDATE OF s,c SKIP LOCKED",
            (MAX_F04_START_ATTEMPTS,),
            )
            rows = cur.fetchall()
            for case_id, revision, generation_id in rows:
                cur.execute(
                "INSERT INTO routing_jobs (job_id,case_id,source_case_revision,source_generation_id,recovery_reason,state) VALUES (%s,%s,%s,%s,'reconciliation','pending') "
                "ON CONFLICT (case_id,source_case_revision) DO NOTHING",
                    (uuid.uuid4(), case_id, revision, generation_id),
                )
            cur.execute(
                "SELECT r.case_id,r.source_case_revision,r.target_unit_id,s.request_type_id "
                "FROM routing_operations r LEFT JOIN case_assignments a "
                "ON a.case_id=r.case_id AND a.source_case_revision=r.source_case_revision "
                "JOIN current_validation_states s ON s.case_id=r.case_id AND s.revision=r.source_case_revision "
                "WHERE a.assignment_id IS NULL ORDER BY r.created_at LIMIT 100 FOR UPDATE OF r SKIP LOCKED"
            )
            assignment_rows = cur.fetchall()
            for case_id, revision, unit_id, request_type_id in assignment_rows:
                _assign_case(cur, case_id, revision, unit_id, request_type_id)
    except psycopg.Error:
        # Validation owns these source tables and can legitimately be starting
        # at the same time.  A later scan repairs this without treating it as a
        # terminal routing rejection.
        return False
    return bool(rows or assignment_rows)


if __name__ == "__main__":
    ensure_schema()
    while True:
        progressed = run_route_once() or run_notification_once()
        if not progressed:
            recover_once()
            time.sleep(POLL_SECONDS)
