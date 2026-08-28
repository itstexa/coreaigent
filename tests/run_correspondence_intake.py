"""Non-mock F-04 acceptance: OCR -> classification -> F-03 -> BGE-M3 -> Jamba."""

import json
import os
import time
import urllib.error
import urllib.request
import uuid

import psycopg


DATABASE_URL = os.environ["DATABASE_URL"]
OCR_URL = "http://ocr:8080/v1/ocr"
VALIDATION_URL = "http://validation:8080/v1/validate"
WORKFLOW_URL = "http://workflow:8080"
AUTH = {"Authorization": "Bearer f03-demo-token"}
ADMIN = {"Authorization": "Bearer f06-demo-admin-token"}


def call(url, payload=None, *, method="POST", headers=None, expected=200):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} | (headers or {}), method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status, body, response_headers = response.status, json.load(response), response.headers
    except urllib.error.HTTPError as exc:
        status, body, response_headers = exc.code, json.load(exc), exc.headers
    assert status == expected, (status, body)
    return body, response_headers


def wait_for_classification(document_id):
    for _ in range(200):
        with psycopg.connect(DATABASE_URL) as db:
            row = db.execute("SELECT status FROM current_classifications WHERE document_id=%s", (document_id,)).fetchone()
            job = db.execute("SELECT state FROM durable_outbox_jobs WHERE document_id=%s", (document_id,)).fetchone()
        if row and job and job[0] == "completed":
            assert row == ("classified",), row
            return
        time.sleep(0.1)
    raise AssertionError("real classification did not complete")


def wait_for_generation(case_id):
    seen_processing = False
    # BGE-M3 is deliberately local and may cold-load on CPU when Jamba occupies
    # the 8 GB GPU.  This is a real-service timeout, not a mock delay.
    for _ in range(720):
        result, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/correspondence", method="GET", headers=AUTH)
        if result["generation_status"] == "processing":
            seen_processing = True
        if result["generation_status"] in {"completed", "failed"}:
            assert result["generation_status"] == "completed", result
            return result, seen_processing
        time.sleep(0.5)
    raise AssertionError("real F-04 generation did not reach a terminal state within six minutes")


def wait_for_case_state(case_id, expected):
    for _ in range(720):
        result, _ = call(f"{WORKFLOW_URL}/cases/{case_id}", method="GET", headers=AUTH)
        if result["state"] == expected:
            return result
        time.sleep(0.5)
    raise AssertionError(f"case did not become {expected} within six minutes")


def wait_for_routing(case_id):
    """Observe F-05's real durable event and two real Jamba notification jobs."""
    for _ in range(720):
        result, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/routing", method="GET", headers=AUTH)
        states = {item["audience"]: item["generation_status"] for item in result.get("notifications", [])}
        if result["routing_status"] == "routed" and states == {"applicant": "completed", "target_unit": "completed"}:
            return result
        if any(state == "failed" for state in states.values()):
            raise AssertionError(f"real F-05 notification failed: {result}")
        time.sleep(0.5)
    raise AssertionError("real F-05 routing did not complete within six minutes")


def main():
    document_id = "f04-real-" + uuid.uuid4().hex
    text = (
        "Belediyeye dilekçe başvurumun sonucu hakkında gerekçeli cevap talep ediyorum. "
        "Gece gürültü desibel rahatsızlık şikayet bildiriyorum.\n"
        "applicant-name: Ayşe Yılmaz\n"
        "tckn: 10000000146\n"
        "incident-address: Atatürk Mahallesi 1. Sokak No: 2\n"
        "incident-date: 25.08.2026\n"
        "incident-description: Gece yüksek ses nedeniyle dinlenemiyoruz."
    )
    ocr, _ = call(OCR_URL, {
        "schemaVersion": "2.0", "requestId": "req-" + document_id,
        "documentId": document_id, "sourceType": "text", "text": text,
        "sourceMetadata": {}, "correlationId": "f04-real",
    })
    wait_for_classification(document_id)
    validation, headers = call(VALIDATION_URL, {
        "schemaVersion": "3.0", "requestId": ocr["requestId"], "documentId": document_id,
        "workflowId": ocr["workflowId"], "status": "classified",
        "department": {"id": "zabita", "label": "Zabıta"},
        "unit": {"id": "denetim", "label": "Denetim"},
        "requestType": {"id": "gurultu-sikayeti", "label": "Gürültü şikayeti"},
        "confidence": 1.0, "taxonomyVersion": "demo-belediyesi-v1",
        "classifierVersion": "real-f04-acceptance", "classificationReason": "worker completed",
    })
    assert validation["completionStatus"] == "complete", validation
    assert headers["ETag"] == '"1"'
    case_id = validation["caseId"]

    # F-06 starts F-04 through the PostgreSQL durable orchestrator, without a
    # frontend POST.  The former F-04 request checks remain negative coverage.
    unauthorized, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/correspondence", {}, headers={"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"1"'}, expected=401)
    assert unauthorized["error"]["code"] == "UNAUTHORIZED", unauthorized
    stale, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/correspondence", {}, headers=AUTH | {"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"2"'}, expected=412)
    assert stale["error"]["code"] == "CASE_REVISION_CONFLICT", stale

    result, seen_processing = wait_for_generation(case_id)
    assert result["case_revision"] == 1 and result["generation_status"] == "completed", result
    assert result["document_summary"] and len(result["document_summary"]) <= 600, result
    assert result["draft_text"] and len(result["draft_text"]) <= 6000, result
    assert result["recommended_correspondence_type"] in {"response_letter", "information_letter", "referral_letter", "cover_letter", "other"}, result
    assert "Ayşe Yılmaz" not in result["draft_text"] and "10000000146" not in result["draft_text"], result
    if result["source_status"] == "relevant_source_found":
        assert result["result_status"] == "draft_ready" and result["regulation_suggestions"], result
        for citation in result["regulation_suggestions"]:
            assert {"source_id", "corpus_version", "title", "source_type", "locator", "chunk_id"} <= set(citation), citation
            assert citation["corpus_version"] == "demo-municipality-regulations-v2", citation
    else:
        assert result["source_status"] == "no_relevant_source" and result["result_status"] == "review_required", result
        assert result["regulation_suggestions"] == [], result

    routed = wait_for_routing(case_id)
    assert routed["case_revision"] == 1 and routed["routing_status"] == "routed", routed
    expected_kind = "classified" if result["result_status"] == "draft_ready" else "fallback"
    assert routed["route_kind"] == expected_kind, routed
    if expected_kind == "fallback":
        assert routed["target_department"]["id"] == "diger" and routed["target_unit"]["id"] == "siniflandirilmamis", routed
    with psycopg.connect(DATABASE_URL) as db:
        route_count = db.execute("SELECT count(*) FROM routing_operations WHERE case_id=%s AND source_case_revision=1", (case_id,)).fetchone()
        notifications = db.execute("SELECT audience,payload FROM notification_records WHERE routing_id=(SELECT routing_id FROM routing_operations WHERE case_id=%s AND source_case_revision=1)", (case_id,)).fetchall()
    assert route_count == (1,), route_count
    payloads = {audience: payload for audience, payload in notifications}
    assert set(payloads) == {"applicant", "target_unit"}, payloads
    assert "case_context" not in payloads["applicant"] and payloads["applicant"]["email_placeholder"] is None, payloads
    assert "case_context" in payloads["target_unit"] and payloads["target_unit"]["email_placeholder"] is None, payloads

    # The demo has exactly two testable tokens: USER can read the case but not
    # operational details or review-complete it; ADMIN can complete review.
    if result["result_status"] == "review_required":
        user_view = wait_for_case_state(case_id, "needs_review")
        assert "operational_context" not in user_view and "target_unit_notification" not in user_view, user_view
        admin_view, _ = call(f"{WORKFLOW_URL}/cases/{case_id}", method="GET", headers=ADMIN)
        assert admin_view["operational_context"]["validated_fields"] and admin_view["target_unit_notification"], admin_view
        denied, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/review-completion", headers=AUTH | {"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"1"'}, expected=403)
        assert denied["error"]["code"] == "FORBIDDEN", denied
        review_headers = ADMIN | {"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"1"'}
        completed, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/review-completion", headers=review_headers)
        replay, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/review-completion", headers=review_headers)
        assert completed == replay == {"case_id": case_id, "case_revision": 1, "state": "completed"}, (completed, replay)
        wait_for_case_state(case_id, "completed")

    changed, changed_headers = call(
        f"http://validation:8080/cases/{case_id}/supplemental-information",
        {"fields": {"phone": "05321234567"}}, method="PATCH",
        headers=AUTH | {"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"1"'},
    )
    assert changed["completionStatus"] == "complete" and changed_headers["ETag"] == '"2"', changed
    # A supplemental revision gets its own automatic F-04 request; the old
    # immutable generation must never be exposed as revision 2's current draft.
    for _ in range(80):
        current, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/correspondence", method="GET", headers=AUTH)
        if current["generation_status"] in {"queued", "processing", "completed", "failed"}:
            break
        time.sleep(0.1)
    assert current["case_revision"] == 2 and current["generation_status"] != "not_requested", current

    with psycopg.connect(DATABASE_URL) as db:
        persisted = db.execute("SELECT generation_status, model_id, model_revision, source_case_revision FROM correspondence_generations WHERE case_id=%s AND source_case_revision=1", (case_id,)).fetchone()
    assert persisted[0] == "completed" and persisted[1] and persisted[2] and persisted[3] == 1, persisted
    print(f"F-04 real correspondence intake: passed (processing_seen={seen_processing}, source_status={result['source_status']})")


if __name__ == "__main__":
    main()
