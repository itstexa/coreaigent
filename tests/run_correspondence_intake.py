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

    not_requested, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/correspondence", method="GET", headers=AUTH)
    assert not_requested == {"case_id": case_id, "case_revision": 1, "generation_status": "not_requested", "result": None}, not_requested
    unauthorized, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/correspondence", {}, headers={"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"1"'}, expected=401)
    assert unauthorized["error"]["code"] == "UNAUTHORIZED", unauthorized
    stale, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/correspondence", {}, headers=AUTH | {"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"2"'}, expected=412)
    assert stale["error"]["code"] == "CASE_REVISION_CONFLICT", stale

    key = str(uuid.uuid4())
    request_headers = AUTH | {"Idempotency-Key": key, "If-Match": '"1"'}
    started, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/correspondence", {}, headers=request_headers, expected=202)
    assert started["case_id"] == case_id and started["case_revision"] == 1 and started["generation_status"] == "queued", started
    replay, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/correspondence", {}, headers=request_headers, expected=202)
    assert replay == started, (replay, started)
    with psycopg.connect(DATABASE_URL) as db:
        assert db.execute("SELECT count(*) FROM correspondence_generation_jobs WHERE generation_id=(SELECT generation_id FROM correspondence_replays WHERE case_id=%s AND idempotency_key=%s)", (case_id, key)).fetchone() == (1,)

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
            assert citation["corpus_version"] == "demo-municipality-regulations-v1", citation
    else:
        assert result["source_status"] == "no_relevant_source" and result["result_status"] == "review_required", result
        assert result["regulation_suggestions"] == [], result

    changed, changed_headers = call(
        f"http://validation:8080/cases/{case_id}/supplemental-information",
        {"fields": {"phone": "05321234567"}}, method="PATCH",
        headers=AUTH | {"Idempotency-Key": str(uuid.uuid4()), "If-Match": '"1"'},
    )
    assert changed["completionStatus"] == "complete" and changed_headers["ETag"] == '"2"', changed
    current, _ = call(f"{WORKFLOW_URL}/cases/{case_id}/correspondence", method="GET", headers=AUTH)
    assert current == {"case_id": case_id, "case_revision": 2, "generation_status": "not_requested", "result": None}, current

    with psycopg.connect(DATABASE_URL) as db:
        persisted = db.execute("SELECT generation_status, model_id, model_revision, source_case_revision FROM correspondence_generations WHERE case_id=%s", (case_id,)).fetchone()
    assert persisted[0] == "completed" and persisted[1] and persisted[2] and persisted[3] == 1, persisted
    print(f"F-04 real correspondence intake: passed (processing_seen={seen_processing}, source_status={result['source_status']})")


if __name__ == "__main__":
    main()
