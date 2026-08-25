"""Real PostgreSQL/worker acceptance checks for F-02."""

import json
import os
import time
import urllib.request
import uuid

import psycopg


DATABASE_URL = os.environ["DATABASE_URL"]


def post(document_id, text):
    payload = {"schemaVersion": "2.0", "requestId": "req-" + document_id, "documentId": document_id, "sourceType": "text", "text": text, "sourceMetadata": {}, "correlationId": "f02"}
    request = urllib.request.Request("http://ocr:8080/v1/ocr", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        assert response.status == 200
        return json.load(response)


def classify_directly(ocr_result):
    request = urllib.request.Request("http://classification:8080/v1/classify", data=json.dumps(ocr_result).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        assert response.status == 200
        return json.load(response)


def wait_for(document_id):
    for _ in range(100):
        with psycopg.connect(DATABASE_URL) as db:
            row = db.execute("SELECT status, department_id, unit_id, request_type_id, confidence::float8 FROM current_classifications WHERE document_id = %s", (document_id,)).fetchone()
            job = db.execute("SELECT state, attempt_count FROM durable_outbox_jobs WHERE document_id = %s", (document_id,)).fetchone()
        if row and job and job[0] == "completed":
            return row, job
        time.sleep(0.1)
    raise AssertionError(f"classification did not complete for {document_id}")


def main():
    run_id = uuid.uuid4().hex
    classified_id = f"f02-classified-{run_id}"
    threshold_id = f"f02-threshold-{run_id}"
    no_match_id = f"f02-no-match-{run_id}"

    classified_ocr = post(classified_id, "Gece gürültü desibel rahatsızlık şikayet bildiriyorum. Bu resmi evrak değerlendirme içindir.")
    direct = classify_directly(classified_ocr)
    assert direct["schemaVersion"] == "3.0", direct
    assert direct["status"] == "classified" and direct["requestType"]["id"] == "gurultu-sikayeti", direct
    assert "topCandidates" not in direct, direct
    row, job = wait_for(classified_id)
    assert row == ("classified", "zabita", "denetim", "gurultu-sikayeti", 1.0), row
    assert job[0] == "completed" and job[1] >= 1, job

    post(threshold_id, "Gece gürültü desibel rahatsızlık bildiriyorum. Bu resmi evrak değerlendirme içindir.")
    row, job = wait_for(threshold_id)
    assert row == ("needs_review", "zabita", "denetim", "gurultu-sikayeti", 0.8), row
    assert job[0] == "completed", job

    post(no_match_id, "Mor bulutlar sessizce ilerler ve uzak tepeleri yavaşça örter, gökyüzü kararır.")
    row, job = wait_for(no_match_id)
    assert row == ("needs_review", None, None, None, 0.0), row
    assert job[0] == "completed", job
    print("F-02 classification intake: passed")


if __name__ == "__main__":
    main()
