"""Real F-06 negative path: a F-02 review case remains observable, not started."""

import json
import os
import time
import urllib.request
import uuid

import psycopg


DATABASE_URL = os.environ["DATABASE_URL"]
OCR_URL = "http://ocr:8080/v1/ocr"
WORKFLOW_URL = "http://workflow:8080"
USER = {"Authorization": "Bearer f03-demo-token", "Content-Type": "application/json"}


def request(url, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=USER, method="POST" if body is not None else "GET"), timeout=30) as response:
        return json.load(response)


def main():
    document_id = "f06-review-" + uuid.uuid4().hex
    request(OCR_URL, {
        "schemaVersion": "2.0", "requestId": "req-" + document_id,
        "documentId": document_id, "sourceType": "text",
        "text": "Bu metin belediye demo sınıflandırma taksonomisinde hiçbir anahtar sözcük içermez ve inceleme gerektirir.",
        "sourceMetadata": {}, "correlationId": "f06-review",
    })
    for _ in range(200):
        with psycopg.connect(DATABASE_URL) as db:
            classified = db.execute("SELECT case_id,status FROM current_classifications WHERE document_id=%s", (document_id,)).fetchone()
            state = db.execute("SELECT state,revision FROM current_case_states WHERE case_id=(SELECT case_id FROM intake_records WHERE document_id=%s)", (document_id,)).fetchone()
            validation = db.execute("SELECT count(*) FROM current_validation_states WHERE document_id=%s", (document_id,)).fetchone()[0]
            starts = db.execute("SELECT count(*) FROM correspondence_start_jobs WHERE case_id=(SELECT case_id FROM intake_records WHERE document_id=%s)", (document_id,)).fetchone()[0]
            routes = db.execute("SELECT count(*) FROM routing_operations WHERE case_id=(SELECT case_id FROM intake_records WHERE document_id=%s)", (document_id,)).fetchone()[0]
        if classified and state:
            assert classified[1] == "needs_review", classified
            assert state == ("needs_review", 1), state
            assert validation == starts == routes == 0, (validation, starts, routes)
            view = request(f"{WORKFLOW_URL}/cases/{classified[0]}")
            assert view["state"] == "needs_review" and view["validation_status"] is None and view["routing_status"] == "not_routed", view
            assert "operational_context" not in view and "target_unit_notification" not in view, view
            print("F-06 real review-state intake: passed")
            return
        time.sleep(0.1)
    raise AssertionError("F-02 review case was not projected by F-06")


if __name__ == "__main__":
    main()
