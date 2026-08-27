"""Deterministic, contract-shaped HTTP mocks; intentionally stdlib-only."""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SERVICE = os.environ.get("MOCK_SERVICE", "ocr")
ROOT = Path("/") if Path("/contracts").exists() else Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "contracts/http/manifest.json").read_text(encoding="utf-8"))["services"]
SCENARIOS = json.loads((ROOT / "scenarios/golden-scenarios.json").read_text(encoding="utf-8"))["scenarios"]
BY_ID = {item["id"]: item for item in SCENARIOS}
CASE_STATE_OVERRIDES = {}


def scenario(payload):
    key = payload.get("scenarioId") or payload.get("documentId", "").removeprefix("doc-")
    return BY_ID.get(key)


def case_parts(path):
    match = re.fullmatch(r"/cases/([^/]+)(?:/(correspondence|routing|review-completion|supplemental-information|document))?", path)
    if not match:
        return None, None, None
    case_id, action = match.groups()
    key = case_id.removeprefix("case-doc-").removeprefix("case-")
    return case_id, action, BY_ID.get(key)


def mock_case_state(item):
    if item["classification"] == "processable":
        return "completed", "complete", ["F-01", "F-02", "F-03", "F-04", "F-05"]
    if item["classification"] == "needs_information":
        return "waiting_for_user", "missing_information", ["F-01", "F-02"]
    return "needs_review", None, ["F-01", "F-02"]


def mock_case_response(case_id, item, admin=False):
    state, validation_status, steps = mock_case_state(item)
    if CASE_STATE_OVERRIDES.get(case_id) == "completed":
        state = "completed"
    response = {
        "case_id": case_id,
        "case_revision": 1,
        "state": state,
        "completed_steps": steps,
        "last_error_code": None,
        "updated_at": "2026-01-01T00:00:00Z",
        "validation_status": validation_status,
        "routing_status": "routed" if item["classification"] == "processable" else "not_routed",
        "applicant_notifications": [] if validation_status != "missing_information" else [{
            "kind": "missing_information",
            "payload": {"kind": "missing_information", "fields": [{"id": "required-attachment", "label": "Zorunlu ek"}], "email_placeholder": None},
            "created_at": "2026-01-01T00:00:00Z",
        }],
    }
    if admin:
        response["operational_context"] = {
            "validated_fields": {},
            "department_id": item["department"],
            "unit_id": "demo-unit-" + item["department"],
            "request_type_id": item["documentType"],
            "document_summary": item["title"] if item["classification"] == "processable" else None,
            "draft_text": item["draft"] if item["classification"] == "processable" else None,
        }
        response["routing"] = None if item["classification"] != "processable" else {
            "target_department_id": item["department"],
            "target_unit_id": "demo-unit-" + item["department"],
        }
        response["target_unit_notification"] = None if item["classification"] != "processable" else {
            "title": "Yeni demo evrakı",
            "body": "Contract mock tarafından kalıcı olmayan bildirim kaydı simüle edildi.",
            "email_placeholder": None,
        }
    return response


def mock_case_document_response(case_id, item):
    """The scenario's own petition text, shaped like the real intake projection."""
    return {
        "case_id": case_id,
        "document_id": "doc-" + item["id"],
        "source_type": "ocr" if item["requiresOcr"] else "text",
        "language": "tr",
        "title": item["title"],
        "channel": "contract-mock",
        "created_at": "2026-01-01T00:00:00Z",
        "text": item["text"],
    }


def mock_correspondence_response(case_id, item):
    if item["classification"] != "processable":
        return {"case_id": case_id, "case_revision": 1, "generation_status": "not_requested", "result": None}
    suggestions = [] if not item["retrieval"] else [{
        "source_id": "REG-MOCK-001", "corpus_version": "mock-regulations-v1",
        "title": "İlgili kamu mevzuatı", "source_type": "mock_contract",
        "locator": "Golden scenario referansı", "chunk_id": "REG-MOCK-001-chunk-001",
    }]
    return {
        "case_id": case_id, "case_revision": 1, "generation_id": "generation-" + item["id"],
        "generation_status": "completed",
        "source_status": "relevant_source_found" if suggestions else "no_relevant_source",
        "result_status": "draft_ready" if suggestions else "review_required",
        "corpus_version": "mock-regulations-v1", "document_summary": item["title"],
        "recommended_correspondence_type": "response_letter", "correspondence_type_detail": None,
        "draft_text": item["draft"], "regulation_suggestions": suggestions,
    }


def mock_routing_response(case_id, item):
    if item["classification"] != "processable":
        return {"case_id": case_id, "case_revision": 1, "routing_status": "not_routed", "result": None}
    return {
        "case_id": case_id, "case_revision": 1, "routing_id": "routing-" + item["id"],
        "routing_status": "routed", "route_kind": "classified",
        "target_department": {"id": item["department"], "label": item["department"]},
        "target_unit": {"id": "demo-unit-" + item["department"], "label": "Demo Birim"},
        "notifications": [
            {"audience": "applicant", "generation_status": "completed", "error_code": None},
            {"audience": "target_unit", "generation_status": "completed", "error_code": None},
        ],
    }


def tracing(payload):
    return {
        "schemaVersion": "2.0",
        "requestId": payload.get("requestId", "unknown-request"),
        "documentId": payload.get("documentId", "unknown-document"),
        "workflowId": payload.get("workflowId") or "wf-" + payload.get("documentId", "unknown-document"),
    }


def result(payload, item):
    trace = tracing(payload)
    if SERVICE == "ocr":
        return trace | {"caseId": "case-" + payload.get("documentId", "unknown-document"), "text": item["text"], "language": "tr", "confidence": 0.91, "ingestStatus": "queued", "warnings": []}
    if SERVICE == "classification":
        trace["schemaVersion"] = "3.0"
        status = "classified" if item["classification"] == "processable" else "needs_review"
        department = {"id": item["department"], "label": item["department"]}
        unit = {"id": "demo-unit-" + item["department"], "label": "Demo Birim"}
        request_type = {"id": item["documentType"], "label": item["title"]}
        return trace | {"status": status, "department": department, "unit": unit, "requestType": request_type, "confidence": 0.91 if status == "classified" else 0.8, "taxonomyVersion": "demo-belediyesi-v1", "classifierVersion": "mock-deterministic-v3", "classificationReason": "Deterministic mock scenario"}
    if SERVICE == "validation":
        trace["schemaVersion"] = "3.0"
        missing = [] if item["classification"] != "needs_information" else [{"id": "required-attachment", "label": "Zorunlu ek"}]
        status = "missing_information" if missing else "complete"
        return trace | {"caseId": "case-" + payload.get("documentId", "unknown-document"), "requestTypeId": item["documentType"], "schemaVersionUsed": "demo-belediyesi-fields-v1", "extractedFields": [], "missingRequiredFields": missing, "invalidFields": [], "completionStatus": status, "userActionRequired": bool(missing)}
    if SERVICE == "rag":
        results = [] if not item["retrieval"] else [{"id": "regulation-" + item["id"], "title": "İlgili kamu mevzuatı", "excerpt": item["title"], "score": 0.9}]
        return trace | {"results": results, "searchedAt": "2026-01-01T00:00:00Z"}
    if SERVICE == "llm":
        return trace | {"output": {"draft": item["draft"], "department": item["department"], "confidence": 0.9}, "model": "mock-deterministic-v1"}
    steps = [{"service": name, "status": "completed" if item["status"] == "completed" or name == "workflow" else "skipped", "timestamp": "2026-01-01T00:00:00Z"} for name in ("ocr", "classification", "validation", "rag", "llm", "workflow")]
    return trace | {"status": item["status"], "documentType": item["documentType"], "department": item["department"], "draft": item["draft"], "steps": steps, "error": None}


def request(service, payload):
    boundary = MANIFEST[service]
    req = urllib.request.Request("http://" + service + ":8080" + boundary["path"], data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read())


def workflow_result(payload, item):
    ocr = request("ocr", payload)
    classification = request("classification", ocr)
    validation = request("validation", classification)
    trace = {key: classification[key] for key in ("schemaVersion", "requestId", "documentId", "workflowId")}
    trace["schemaVersion"] = "2.0"
    rag = request("rag", trace | {"query": classification["requestType"]["label"], "documentType": item["documentType"]})
    llm = request("llm", trace | {"task": "draft_reply", "prompt": payload["text"], "context": [entry["excerpt"] for entry in rag["results"]]})
    steps = [{"service": name, "status": "completed", "timestamp": "2026-01-01T00:00:00Z"} for name in ("ocr", "classification", "validation", "rag", "llm", "workflow")]
    return trace | {"status": item["status"], "documentType": item["documentType"], "department": llm["output"]["department"], "draft": llm["output"]["draft"], "steps": steps, "error": None}


def matches(schema, value):
    """The contracts use only this small JSON Schema subset; full checks run in tests."""
    if "const" in schema and value != schema["const"]: return False
    if "enum" in schema and value not in schema["enum"]: return False
    types = schema.get("type")
    if types:
        types = types if isinstance(types, list) else [types]
        python_types = {"object": dict, "array": list, "string": str, "number": (int, float), "integer": int, "boolean": bool, "null": type(None)}
        if not any(isinstance(value, python_types[name]) and not (name in ("number", "integer") and isinstance(value, bool)) for name in types): return False
    if isinstance(value, dict):
        if not set(schema.get("required", [])) <= value.keys(): return False
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False and not value.keys() <= props.keys(): return False
        if not all(matches(props[key], item) for key, item in value.items() if key in props): return False
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0): return False
        if "items" in schema and not all(matches(schema["items"], item) for item in value): return False
    if isinstance(value, str) and len(value) < schema.get("minLength", 0): return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", value) or value > schema.get("maximum", value): return False
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_json(self, status, body, headers=None):
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-CoreAIgent-Implementation", "mock")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path in ("/health", "/ready"):
            self.send_json(200, {"status": "ready", "service": SERVICE, "implementation": "mock"})
        elif SERVICE == "workflow":
            case_id, action, item = case_parts(self.path)
            if not item:
                self.send_json(404, {"error": {"code": "CASE_NOT_FOUND", "message": "Mock case was not found"}})
            elif action == "correspondence":
                self.send_json(200, mock_correspondence_response(case_id, item))
            elif action == "routing":
                self.send_json(200, mock_routing_response(case_id, item))
            elif action == "document":
                if self.headers.get("Authorization") != "Bearer f06-demo-admin-token":
                    self.send_json(403, {"error": {"code": "FORBIDDEN", "message": "ADMIN authorization is required"}})
                else:
                    self.send_json(200, mock_case_document_response(case_id, item))
            elif action is None:
                admin = self.headers.get("Authorization") == "Bearer f06-demo-admin-token"
                self.send_json(200, mock_case_response(case_id, item, admin))
            else:
                self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "Mock route was not found"}})
        else:
            self.send_json(404, {"error": "not_found"})

    def do_PATCH(self):
        case_id, action, item = case_parts(self.path)
        if SERVICE != "validation" or action != "supplemental-information" or not item:
            self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "Mock route was not found"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            fields = payload["fields"]
            assert isinstance(fields, dict) and fields
        except (ValueError, KeyError, AssertionError, json.JSONDecodeError):
            self.send_json(400, {"error": {"code": "REQUEST_BODY_INVALID", "message": "fields must be a non-empty object"}})
            return
        body = {
            "schemaVersion": "3.0", "requestId": "supplemental-mock", "documentId": "doc-" + item["id"],
            "caseId": case_id, "workflowId": "wf-doc-" + item["id"], "requestTypeId": item["documentType"],
            "schemaVersionUsed": "demo-belediyesi-fields-v1",
            "extractedFields": [{"id": key, "label": key, "value": value, "confidence": 1.0} for key, value in fields.items()],
            "missingRequiredFields": [], "invalidFields": [], "completionStatus": "complete", "userActionRequired": False,
        }
        self.send_json(200, body, {"ETag": '"2"'})

    def do_POST(self):
        case_id, action, case_item = case_parts(self.path)
        if SERVICE == "workflow" and case_item and action == "correspondence":
            if case_item["classification"] != "processable":
                self.send_json(409, {"error": {"code": "CASE_NOT_READY_FOR_CORRESPONDENCE", "message": "Mock case is not ready"}})
            else:
                self.send_json(202, {"case_id": case_id, "job_id": "job-" + case_item["id"], "case_revision": 1, "generation_status": "queued"})
            return
        if SERVICE == "workflow" and case_item and action == "review-completion":
            CASE_STATE_OVERRIDES[case_id] = "completed"
            self.send_json(200, {"case_id": case_id, "case_revision": 1, "state": "completed"})
            return
        expected = MANIFEST[SERVICE]["path"]
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            payload = {}
        item = scenario(payload)
        schema = json.loads((ROOT / "contracts/schemas" / (MANIFEST[SERVICE]["request"] + ".schema.json")).read_text(encoding="utf-8"))
        if self.path != expected or not matches(schema, payload) or not item:
            error = {"schemaVersion": "2.0", "requestId": payload.get("requestId", "unknown-request"), "workflowId": payload.get("workflowId"), "documentId": payload.get("documentId"), "service": SERVICE, "timestamp": "2026-01-01T00:00:00Z", "category": "validation", "message": "Invalid request, unknown scenario, or endpoint", "retryable": False}
            print(json.dumps({"timestamp": error["timestamp"], "requestId": error["requestId"], "workflowId": error["workflowId"], "documentId": error["documentId"], "service": SERVICE, "errorCategory": "validation"}), flush=True)
            self.send_json(400 if self.path == expected else 404, error)
            return
        try:
            body = workflow_result(payload, item) if SERVICE == "workflow" else result(payload, item)
        except Exception as exc:
            error = {"schemaVersion": "2.0", "requestId": payload["requestId"], "workflowId": payload.get("workflowId") or "wf-" + payload["documentId"], "documentId": payload["documentId"], "service": SERVICE, "timestamp": "2026-01-01T00:00:00Z", "category": "dependency", "message": str(exc), "retryable": True}
            print(json.dumps({"timestamp": error["timestamp"], "requestId": error["requestId"], "workflowId": error["workflowId"], "documentId": error["documentId"], "service": SERVICE, "errorCategory": "dependency"}), flush=True)
            self.send_json(502, error)
            return
        print(json.dumps({"timestamp": "2026-01-01T00:00:00Z", "requestId": payload["requestId"], "workflowId": payload.get("workflowId") or "wf-" + payload["documentId"], "documentId": payload["documentId"], "service": SERVICE, "errorCategory": None}), flush=True)
        self.send_json(200, body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
