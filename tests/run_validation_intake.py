"""Real OCR/classification/validation acceptance checks for F-03."""

import argparse
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


def call(url, payload, *, method="POST", headers=None, expected=200):
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"} | (headers or {}), method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status, body, response_headers = response.status, json.load(response), response.headers
    except urllib.error.HTTPError as exc:
        status, body, response_headers = exc.code, json.load(exc), exc.headers
    assert status == expected, (status, body)
    return body, response_headers


def submit(document_id, text, metadata=None):
    body = {"schemaVersion": "2.0", "requestId": "req-" + document_id, "documentId": document_id, "sourceType": "text", "text": text, "sourceMetadata": metadata or {}, "correlationId": "f03"}
    return call(OCR_URL, body)[0]


def wait_classified(document_id):
    for _ in range(100):
        with psycopg.connect(DATABASE_URL) as db:
            row = db.execute("SELECT status, request_type_id FROM current_classifications WHERE document_id = %s", (document_id,)).fetchone()
            job = db.execute("SELECT state FROM durable_outbox_jobs WHERE document_id = %s", (document_id,)).fetchone()
        if row and job and job[0] == "completed":
            assert row == ("classified", "gurultu-sikayeti"), row
            return
        time.sleep(0.1)
    raise AssertionError("classification worker did not complete")


def validate(ocr_result, expected=200):
    return call(VALIDATION_URL, {"schemaVersion": "3.0", **{key: ocr_result[key] for key in ("requestId", "documentId", "workflowId")}, "status": "classified", "department": {"id": "zabita", "label": "Zabıta"}, "unit": {"id": "denetim", "label": "Denetim"}, "requestType": {"id": "gurultu-sikayeti", "label": "Gürültü şikayeti"}, "confidence": 1.0, "taxonomyVersion": "demo-belediyesi-v1", "classifierVersion": "acceptance", "classificationReason": "worker completed"}, expected=expected)


def assert_public_result(result):
    assert result["schemaVersion"] == "3.0"
    assert {"evidence", "provenance", "sourceText", "topCandidates"}.isdisjoint(result)
    for field in result["extractedFields"]:
        assert set(field) == {"id", "label", "value", "confidence"}
        assert 0 <= field["confidence"] <= 1


def full_acceptance():
    complete_id = "f03-complete-" + uuid.uuid4().hex
    complete = submit(complete_id, "Gece gürültü desibel rahatsızlık şikayet bildiriyorum.\napplicant-name: Ayşe Yılmaz\ntckn: 10000000146\nincident-address: Atatürk Mahallesi 1. Sokak No: 2\nincident-date: 25.08.2026\nincident-description: Gece yüksek ses nedeniyle dinlenemiyoruz.")
    wait_classified(complete_id)
    result, headers = validate(complete)
    assert_public_result(result)
    assert result["completionStatus"] == "complete" and result["userActionRequired"] is False, result
    assert headers["ETag"] == '"1"'
    assert {field["id"] for field in result["extractedFields"]} >= {"applicant-name", "tckn", "incident-address", "incident-date", "incident-description"}

    missing_id = "f03-missing-" + uuid.uuid4().hex
    missing_ocr = submit(missing_id, "Gece gürültü desibel rahatsızlık şikayet bildiriyorum. tckn: 10000000146")
    wait_classified(missing_id)
    missing, headers = validate(missing_ocr)
    assert missing["completionStatus"] == "missing_information" and missing["userActionRequired"] is True, missing
    assert {field["id"] for field in missing["missingRequiredFields"]} == {"applicant-name", "incident-address", "incident-date", "incident-description"}, missing
    assert headers["ETag"] == '"1"'

    case_url = "http://validation:8080/cases/" + missing["caseId"] + "/supplemental-information"
    first_key = str(uuid.uuid4())
    patch_fields = {"fields": {"applicant-name": "Ayşe Yılmaz", "incident-address": "Atatürk Mahallesi 1. Sokak No: 2", "incident-date": "2026-08-25", "incident-description": "Gece yüksek ses nedeniyle dinlenemiyoruz.", "phone": "05321234567"}}
    patch_headers = {"Authorization": "Bearer f03-demo-token", "Idempotency-Key": first_key, "If-Match": '"1"'}
    merged, merged_headers = call(case_url, patch_fields, method="PATCH", headers=patch_headers)
    assert merged["completionStatus"] == "complete" and merged_headers["ETag"] == '"2"', merged
    assert next(field for field in merged["extractedFields"] if field["id"] == "phone")["value"] == "+905321234567"

    replay, replay_headers = call(case_url, patch_fields, method="PATCH", headers=patch_headers)
    assert replay == merged and replay_headers["ETag"] == '"2"'
    conflict, _ = call(case_url, {"fields": {"phone": "05321111111"}}, method="PATCH", headers=patch_headers, expected=409)
    assert conflict["category"] == "validation"

    invalid, invalid_headers = call(case_url, {"fields": {"phone": "02121234567"}}, method="PATCH", headers={"Authorization": "Bearer f03-demo-token", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"2"'})
    assert invalid["completionStatus"] == "invalid_information" and invalid_headers["ETag"] == '"3"', invalid
    assert invalid["invalidFields"] == [{"id": "phone", "label": "Telefon", "code": "phone_format"}]
    assert next(field for field in invalid["extractedFields"] if field["id"] == "phone")["value"] == "+905321234567"
    stale, _ = call(case_url, {"fields": {"phone": "05321234567"}}, method="PATCH", headers={"Authorization": "Bearer f03-demo-token", "Idempotency-Key": str(uuid.uuid4()), "If-Match": '"2"'}, expected=412)
    assert stale["category"] == "validation"
    with psycopg.connect(DATABASE_URL) as db:
        row = db.execute("SELECT completion_status, revision, accepted_fields->'phone'->>'value' FROM current_validation_states WHERE case_id = %s", (missing["caseId"],)).fetchone()
        assert row == ("invalid_information", 3, "+905321234567"), row

    review_id = "f03-review-" + uuid.uuid4().hex
    review_ocr = submit(review_id, "Mor bulutlar sessizce ilerler ve uzak tepeleri yavaşça örter, gökyüzü kararır.")
    for _ in range(100):
        with psycopg.connect(DATABASE_URL) as db:
            row = db.execute("SELECT status FROM current_classifications WHERE document_id = %s", (review_id,)).fetchone()
        if row:
            break
        time.sleep(0.1)
    assert row == ("needs_review",), row
    rejected, _ = validate(review_ocr, expected=409)
    assert rejected["category"] == "validation"
    with psycopg.connect(DATABASE_URL) as db:
        assert db.execute("SELECT count(*) FROM current_validation_states WHERE document_id = %s", (review_id,)).fetchone() == (0,)


def restart_create():
    document_id = "f03-validation-restart"
    result = submit(document_id, "Gece gürültü desibel rahatsızlık şikayet bildiriyorum.\ntckn: 10000000146")
    wait_classified(document_id)
    validation, headers = validate(result)
    assert validation["completionStatus"] == "missing_information" and headers["ETag"] == '"1"', validation


def restart_verify():
    document_id = "f03-validation-restart"
    with psycopg.connect(DATABASE_URL) as db:
        row = db.execute("SELECT document_id, workflow_id FROM intake_records WHERE document_id = %s", (document_id,)).fetchone()
        state = db.execute("SELECT completion_status, revision, accepted_fields->'tckn'->>'value' FROM current_validation_states WHERE document_id = %s", (document_id,)).fetchone()
    assert row is not None and state == ("missing_information", 1, "10000000146"), (row, state)
    validation, headers = validate({"requestId": "restart-verify", "documentId": row[0], "workflowId": str(row[1])})
    assert validation["completionStatus"] == "missing_information" and headers["ETag"] == '"1"', validation
    with psycopg.connect(DATABASE_URL) as db:
        assert db.execute("SELECT revision FROM current_validation_states WHERE document_id = %s", (document_id,)).fetchone() == (1,)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("all", "restart-create", "restart-verify"), default="all")
    phase = parser.parse_args().phase
    if phase == "all":
        full_acceptance()
    elif phase == "restart-create":
        restart_create()
    else:
        restart_verify()
    print(f"F-03 validation intake {phase}: passed")
