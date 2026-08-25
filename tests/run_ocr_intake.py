import argparse
import json
import os
import time
import urllib.error
import urllib.request
import uuid

import psycopg


OCR_URL = "http://ocr:8080/v1/ocr"
DATABASE_URL = os.environ["DATABASE_URL"]


def payload(document_id, text, *, request_id=None, source_type="text", metadata=None, correlation_id="corr-f01"):
    body = {
        "schemaVersion": "2.0",
        "requestId": request_id or f"request-{document_id}",
        "documentId": document_id,
        "sourceType": source_type,
        "text": text,
        "correlationId": correlation_id,
    }
    if metadata is not None:
        body["sourceMetadata"] = metadata
    return body


def post(body, expected_status=200):
    request = urllib.request.Request(
        OCR_URL,
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status, data = response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        status, data = error.code, json.loads(error.read())
    assert status == expected_status, (status, data)
    return data


def one(sql, *params):
    for attempt in range(20):
        try:
            with psycopg.connect(DATABASE_URL) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(sql, params)
                    return cursor.fetchone()
        except psycopg.OperationalError:
            if attempt == 19:
                raise
            time.sleep(0.25)


def text_of_length(length):
    return "ş" + "a" * (length - 1)


def assert_result(result, document_id):
    assert result["schemaVersion"] == "2.0"
    assert result["documentId"] == document_id
    assert result["ingestStatus"] == "queued"
    assert result["warnings"] == []
    assert result["language"] == "tr"
    assert result["confidence"] == 1.0
    uuid.UUID(result["caseId"])
    uuid.UUID(result["workflowId"])


def assert_count(document_id, expected):
    record_count, job_count = one(
        "SELECT (SELECT count(*) FROM intake_records WHERE document_id = %s), "
        "(SELECT count(*) FROM durable_outbox_jobs WHERE document_id = %s)",
        document_id,
        document_id,
    )
    assert (record_count, job_count) == (expected, expected)


def full_acceptance():
    too_short_id = "f01-39"
    too_short = post(payload(too_short_id, text_of_length(39)), 400)
    assert too_short["category"] == "validation"
    assert too_short["retryable"] is False
    assert_count(too_short_id, 0)

    exact_id = "f01-40"
    exact = post(payload(exact_id, text_of_length(40), metadata={}), 200)
    assert_result(exact, exact_id)
    assert_count(exact_id, 1)

    normalized_id = "f01-normalized"
    original = "S\u0327ikayet\r\n" + "a" * 40
    normalized = "Şikayet\n" + "a" * 40
    normalized_result = post(
        payload(normalized_id, original, metadata={"channel": "citizen_portal"}), 200
    )
    assert_result(normalized_result, normalized_id)
    assert normalized_result["text"] == normalized
    stored = one(
        "SELECT original_text, normalized_text, source_type, source_metadata, correlation_id, ingest_status "
        "FROM intake_records WHERE document_id = %s",
        normalized_id,
    )
    assert stored == (original, normalized, "text", {"channel": "citizen_portal"}, "corr-f01", "queued")

    above_id = "f01-41"
    above = post(payload(above_id, text_of_length(41)), 200)
    assert_result(above, above_id)
    assert_count(above_id, 1)

    ocr_id = "f01-ocr"
    ocr = post(
        payload(ocr_id, text_of_length(40), source_type="ocr", metadata={"page": 2, "engine": "tesseract"}),
        200,
    )
    assert_result(ocr, ocr_id)
    assert one("SELECT source_type, source_metadata FROM intake_records WHERE document_id = %s", ocr_id) == (
        "ocr",
        {"page": 2, "engine": "tesseract"},
    )

    replay_id = "f01-replay"
    first = post(payload(replay_id, text_of_length(40), metadata={"origin": "first"}), 200)
    replay = post(
        payload(replay_id, text_of_length(40), request_id="request-f01-replay-again", metadata={"origin": "first"}),
        200,
    )
    assert first["caseId"] == replay["caseId"]
    assert first["workflowId"] == replay["workflowId"]
    assert first["text"] == replay["text"]
    assert_count(replay_id, 1)

    changed_requests = (
        payload(replay_id, text_of_length(41), metadata={"origin": "first"}),
        payload(replay_id, text_of_length(40), metadata={"origin": "changed"}),
        payload(replay_id, text_of_length(40), source_type="ocr", metadata={"origin": "first"}),
        payload(replay_id, text_of_length(40), metadata={"origin": "first"}, correlation_id="corr-f01-changed"),
    )
    for changed_request in changed_requests:
        changed = post(changed_request, 409)
        assert changed["category"] == "validation"
        assert changed["retryable"] is False
    assert_count(replay_id, 1)
    assert one("SELECT original_text, source_metadata FROM intake_records WHERE document_id = %s", replay_id) == (
        text_of_length(40),
        {"origin": "first"},
    )


def restart_create():
    document_id = "f01-restart"
    result = post(payload(document_id, text_of_length(40), metadata={"phase": "before-restart"}), 200)
    assert_result(result, document_id)
    assert_count(document_id, 1)


def restart_verify():
    document_id = "f01-restart"
    stored = one(
        "SELECT case_id, workflow_id, original_text, normalized_text, ingest_status FROM intake_records WHERE document_id = %s",
        document_id,
    )
    assert stored is not None
    assert stored[2:] == (text_of_length(40), text_of_length(40), "queued")
    assert one("SELECT state, attempt_count FROM durable_outbox_jobs WHERE document_id = %s", document_id) == ("pending", 0)
    replay = post(
        payload(document_id, text_of_length(40), request_id="request-f01-restart-after", metadata={"phase": "before-restart"}),
        200,
    )
    assert replay["caseId"] == str(stored[0])
    assert replay["workflowId"] == str(stored[1])
    assert_count(document_id, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("all", "restart-create", "restart-verify"), default="all")
    phase = parser.parse_args().phase
    if phase == "all":
        full_acceptance()
    elif phase == "restart-create":
        restart_create()
    else:
        restart_verify()
    print(f"F-01 OCR intake {phase}: passed")


if __name__ == "__main__":
    main()
