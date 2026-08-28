"""Deterministic, contract-shaped HTTP mocks; intentionally stdlib-only."""
import json
import os
import re
import urllib.request
import urllib.parse
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
    match = re.fullmatch(r"/cases/([^/]+)(?:/(correspondence|routing|review-completion|supplemental-information|document|action-log|training-export|history|resolution-mark|attachments|abuse|abuse-override|edit|revisions|priority|priority-override|routing-evaluation|routing-feedback))?", path)
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
        "assignee": None,
        "notifications": [
            {"audience": "applicant", "generation_status": "completed", "error_code": None},
            {"audience": "target_unit", "generation_status": "completed", "error_code": None},
        ],
    }


def mock_action_log_response(case_id, item):
    return {
        "case_id": case_id,
        "events": [{
            "event_id": "00000000-0000-4000-8000-000000000001",
            "action_type": "state_change",
            "actor": "mock-workflow",
            "occurred_at": "2026-01-01T00:00:00Z",
            "details": {"state": "received"},
        }],
    }


def mock_training_export_response(case_id, item):
    return {
        "case_id": case_id,
        "document_id": "doc-" + item["id"],
        "text": "Anonimleştirilmiş demo evrakı",
        "redactions": [],
    }


def mock_history_response(case_id, item):
    return {"case_id": case_id, "resolved": False, "resolved_by": [], "similar_cases": []}

def mock_abuse_response(case_id, item):
    return {
        "case_id": case_id, "label": "clear", "confidence": 0.0, "risk_score": 0.0,
        "flagged": False, "detected_signals": [], "override_flagged": None,
        "override_reason": None, "effective_flagged": False,
        "analyzed_at": "2026-01-01T00:00:00Z", "override_at": None,
    }


def mock_attachments_response(case_id, item):
    return {"case_id": case_id, "state": "draft_prepared", "request_type_id": item["documentType"], "missing_required_types": [], "attachments": [], "relations": [], "suggestions": []}


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
        if SERVICE == "workflow" and self.path.split("?", 1)[0] == "/personnel-dashboard":
            if self.headers.get("Authorization") != "Bearer f06-demo-admin-token":
                self.send_json(403, {"error": {"code": "FORBIDDEN", "message": "ADMIN authorization is required"}}); return
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            scope = query.get("scope", ["system"])[0]; period = query.get("period_days", ["30"])[0]
            if scope not in {"unit", "system"} or period not in {"7", "30", "90"} or (scope == "unit" and not query.get("unit_id")):
                self.send_json(400, {"error": {"code": "QUERY_INVALID", "message": "invalid dashboard query"}}); return
            self.send_json(200, {"scope": scope, "unit_id": query.get("unit_id", [None])[0] if scope == "unit" else None, "period_days": int(period), "metrics": {"active_personnel": 3, "open_assignments": 2, "completed_cases": 5, "throughput": 5 / int(period), "average_resolution_hours": None}}); return
        if SERVICE == "workflow" and self.path.split("?", 1)[0] == "/cases":
            if self.headers.get("Authorization") != "Bearer f06-demo-admin-token":
                self.send_json(403, {"error": {"code": "FORBIDDEN", "message": "ADMIN authorization is required"}}); return
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            try:
                limit = max(1, min(100, int(query.get("limit", [25])[0])))
                offset = max(0, int(query.get("offset", [0])[0]))
            except (TypeError, ValueError):
                self.send_json(400, {"error": {"code": "QUERY_INVALID", "message": "invalid pagination query"}}); return
            state_filter = query.get("state", [""])[0]
            search = query.get("q", [""])[0].casefold()
            labels = {
                "petition": "Dilekçe", "application": "Başvuru", "complaint": "Şikâyet",
                "information_request": "Bilgi edinme", "official_letter": "Resmî yazı",
                "invoice": "Fatura", "unsupported": "Desteklenmeyen evrak",
            }
            rows = []
            for item in SCENARIOS:
                state, validation_status, steps = mock_case_state(item)
                row = {
                    "case_id": "case-" + item["id"], "case_revision": 1, "state": state,
                    "completed_steps": steps, "last_error_code": None,
                    "updated_at": "2026-01-01T00:00:00Z", "validation_status": validation_status,
                    "routing_status": "routed" if item["classification"] == "processable" else "not_routed",
                    "document_id": "doc-" + item["id"], "request_type_id": item["documentType"],
                    "request_type_label": labels.get(item["documentType"], item["documentType"]),
                    "department_id": item["department"], "department_label": item["department"],
                    "unit_id": "demo-unit-" + item["department"], "unit_label": "Demo " + item["department"],
                    "classification_status": "classified" if item["classification"] != "needs_review" else "needs_review",
                    "classification_confidence": 0.91 if item["classification"] == "processable" else 0.42,
                    "applicant_name": None, "title": item["title"], "channel": "citizen-portal",
                    "language": "tr", "created_at": "2026-01-01T00:00:00Z",
                    "classification_reason": "Golden senaryo sınıflandırma sonucu.",
                }
                haystack = " ".join(str(row.get(key) or "") for key in ("case_id", "document_id", "title", "applicant_name"))
                if state_filter and state != state_filter: continue
                if search and search not in haystack.casefold(): continue
                rows.append(row)
            self.send_json(200, {"total": len(rows), "limit": limit, "offset": offset, "cases": rows[offset:offset + limit]}); return
        if self.path in ("/health", "/ready"):
            self.send_json(200, {"status": "ready", "service": SERVICE, "implementation": "mock"})
        elif SERVICE == "workflow":
            if self.path == "/moderation-trends":
                if self.headers.get("Authorization") != "Bearer f06-demo-admin-token":
                    self.send_json(403, {"error": {"code": "FORBIDDEN", "message": "ADMIN authorization is required"}})
                else:
                    self.send_json(200, {"status": "no_data", "scope": "system", "period_days": 30, "points": []})
                return
            if self.path == "/routing-evaluation":
                if self.headers.get("Authorization") != "Bearer f06-demo-admin-token":
                    self.send_json(403, {"error": {"code": "FORBIDDEN", "message": "ADMIN authorization is required"}})
                else:
                    self.send_json(200, {"aggregates": []})
                return
            if self.path == "/personnel-dashboard":
                if self.headers.get("Authorization") != "Bearer f06-demo-admin-token":
                    self.send_json(403, {"error": {"code": "FORBIDDEN", "message": "ADMIN authorization is required"}})
                else:
                    self.send_json(200, {"scope": "system", "period_days": 30, "metrics": {"active": 0, "assigned": 0, "completed": 0, "throughput": 0, "average_resolution_hours": 0.0}})
                return
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
            elif action == "action-log":
                if self.headers.get("Authorization") not in {"Bearer f06-demo-user-token", "Bearer f06-demo-admin-token"}:
                    self.send_json(401, {"error": {"code": "UNAUTHORIZED", "message": "Bearer authorization is required"}})
                else:
                    self.send_json(200, mock_action_log_response(case_id, item))
            elif action == "training-export":
                if self.headers.get("Authorization") not in {"Bearer f06-demo-user-token", "Bearer f06-demo-admin-token"}:
                    self.send_json(401, {"error": {"code": "UNAUTHORIZED", "message": "Bearer authorization is required"}})
                else:
                    self.send_json(200, mock_training_export_response(case_id, item))
            elif action == "history":
                if self.headers.get("Authorization") not in {"Bearer f06-demo-user-token", "Bearer f06-demo-admin-token"}:
                    self.send_json(401, {"error": {"code": "UNAUTHORIZED", "message": "Bearer authorization is required"}})
                else:
                    self.send_json(200, mock_history_response(case_id, item))
            elif action == "abuse":
                if self.headers.get("Authorization") != "Bearer f06-demo-admin-token":
                    self.send_json(403, {"error": {"code": "FORBIDDEN", "message": "Moderator authorization is required"}})
                else:
                    self.send_json(200, mock_abuse_response(case_id, item))
            elif action == "attachments":
                if self.headers.get("Authorization") not in {"Bearer f06-demo-user-token", "Bearer f06-demo-admin-token"}:
                    self.send_json(401, {"error": {"code": "UNAUTHORIZED", "message": "Bearer authorization is required"}})
                else:
                    self.send_json(200, mock_attachments_response(case_id, item))
            elif action == "revisions":
                if self.headers.get("Authorization") not in {"Bearer f06-demo-user-token", "Bearer f06-demo-admin-token"}:
                    self.send_json(401, {"error": {"code": "UNAUTHORIZED", "message": "Bearer authorization is required"}})
                else:
                    self.send_json(200, {"case_id": case_id, "revisions": []})
            elif action == "priority":
                if self.headers.get("Authorization") not in {"Bearer f06-demo-user-token", "Bearer f06-demo-admin-token"}:
                    self.send_json(401, {"error": {"code": "UNAUTHORIZED", "message": "Bearer authorization is required"}})
                else:
                    self.send_json(200, {"case_id": case_id, "level": "normal", "policy_version": "priority-policy-v1", "reason": "no qualifying urgency signal; default priority", "override_reason": None, "updated_at": None})
            elif action == "routing-evaluation":
                if self.headers.get("Authorization") not in {"Bearer f06-demo-user-token", "Bearer f06-demo-admin-token"}:
                    self.send_json(401, {"error": {"code": "UNAUTHORIZED", "message": "Bearer authorization is required"}})
                else:
                    self.send_json(200, {"case_id": case_id, "feedback": None})
            elif action is None:
                admin = self.headers.get("Authorization") == "Bearer f06-demo-admin-token"
                self.send_json(200, mock_case_response(case_id, item, admin))
            else:
                self.send_json(404, {"error": {"code": "NOT_FOUND", "message": "Mock route was not found"}})
        else:
            self.send_json(404, {"error": "not_found"})

    def do_PATCH(self):
        case_id, action, item = case_parts(self.path)
        if SERVICE == "workflow" and action == "edit" and item:
            if self.headers.get("Authorization") not in {"Bearer f06-demo-user-token", "Bearer f06-demo-admin-token"}:
                self.send_json(401, {"error":{"code":"UNAUTHORIZED","message":"Bearer authorization is required"}}); return
            if self.headers.get("If-Match") != '"1"':
                self.send_json(412, {"error":{"code":"CASE_REVISION_CONFLICT","message":"If-Match does not match current case revision"}}); return
            self.send_json(200, {"case_id":case_id,"case_revision":2,"parent_revision":1,"document_id":"doc-"+item["id"]+"-revision-2","state":mock_case_state(item)[0],"change_kind":"petition_edit"}, {"ETag":'"2"'})
            return
        if SERVICE == "workflow" and action == "priority-override" and item:
            if self.headers.get("Authorization") != "Bearer f06-demo-admin-token":
                self.send_json(403, {"error": {"code": "FORBIDDEN", "message": "ADMIN authorization is required"}}); return
            try:
                length = int(self.headers.get("Content-Length", "0")); body = json.loads(self.rfile.read(length))
                if body.get("level") not in {"low", "normal", "high", "urgent"} or not str(body.get("reason", "")).strip(): raise ValueError
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                self.send_json(422, {"error": {"code": "PRIORITY_OVERRIDE_INVALID", "message": "level and non-empty reason are required"}}); return
            self.send_json(200, {"case_id": case_id, "level": body["level"], "reason": body["reason"].strip(), "actor": "ADMIN"}); return
        if SERVICE == "workflow" and action == "routing-feedback" and item:
            if self.headers.get("Authorization") != "Bearer f06-demo-admin-token":
                self.send_json(403, {"error": {"code": "FORBIDDEN", "message": "ADMIN authorization is required"}}); return
            try:
                length = int(self.headers.get("Content-Length", "0")); body = json.loads(self.rfile.read(length)); accepted = body["accepted_unit_id"]
                if not isinstance(accepted, str) or not accepted.strip(): raise ValueError
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                self.send_json(400, {"error": {"code": "FEEDBACK_INVALID", "message": "accepted_unit_id is required"}}); return
            self.send_json(200, {"case_id": case_id, "predicted_unit_id": "demo-unit", "accepted_unit_id": accepted, "confidence": 0.8, "confidence_threshold": 0.8, "needs_review": False, "routing_correct": accepted == "demo-unit", "training_eligible": False}); return
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
        if SERVICE == "workflow" and self.path == "/v1/normalize":
            try:
                length = int(self.headers.get("Content-Length", "0")); payload = json.loads(self.rfile.read(length))
                text = payload["text"]
                if payload.get("language", "tr") not in {"tr", "tur"}: self.send_json(200, {"status":"unsupported_language","original_text":text,"suggested_text":None,"changed":False}); return
                if not isinstance(text, str) or not text.strip(): raise ValueError
                normalized = " ".join(text.strip().split())
                self.send_json(200, {"status":"ok","original_text":text,"suggested_text":normalized,"changed":normalized != text}); return
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                self.send_json(422, {"error":"invalid_text"}); return
        if SERVICE == "workflow" and self.path == "/v1/drafts":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                dtype = payload.get("document_type")
                if dtype not in {"petition/request", "complaint", "information_request"}:
                    raise ValueError("unsupported_document_type")
                fields = payload.get("fields") or {}
                missing = [k for k in ("subject", "body", "full_name", "contact") if not isinstance(fields.get(k), str) or not fields[k].strip()]
                self.send_json(200, {"draft_id":"draft-mock","document_type":dtype,"template_version":"bx07-local-templates-v1","fields":fields,"text":"KONU: %s\n\n%s" % (fields.get("subject", ""), fields.get("body", payload.get("text", ""))),"missing_fields":missing,"temporary":True,"editable":True,"legal_finality":False})
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                self.send_json(422, {"error":"unsupported_document_type"})
            return
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
        if SERVICE == "workflow" and case_item and action == "resolution-mark":
            if self.headers.get("Authorization") not in {"Bearer f06-demo-user-token", "Bearer f06-demo-admin-token"}:
                self.send_json(401, {"error": {"code": "UNAUTHORIZED", "message": "Bearer authorization is required"}})
            else:
                self.send_json(200, {"case_id": case_id, "resolved": True, "actor": "USER", "marked_at": "2026-01-01T00:00:00Z"})
            return
        if SERVICE == "workflow" and case_item and action == "abuse-override":
            if self.headers.get("Authorization") != "Bearer f06-demo-admin-token":
                self.send_json(403, {"error": {"code": "FORBIDDEN", "message": "ADMIN authorization is required"}})
            else:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length))
                    if set(body) != {"flagged", "reason"} or not isinstance(body["flagged"], bool) or not isinstance(body["reason"], str) or not body["reason"].strip():
                        raise ValueError
                except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                    self.send_json(400, {"error": {"code": "REQUEST_BODY_INVALID", "message": "flagged and non-empty reason are required"}})
                    return
                self.send_json(200, {"case_id": case_id, "override_flagged": body["flagged"], "reason": body["reason"].strip(), "actor": "ADMIN", "overridden_at": "2026-01-01T00:00:00Z"})
            return
        if SERVICE == "workflow" and case_item and action == "attachments":
            if self.headers.get("Authorization") not in {"Bearer f06-demo-user-token", "Bearer f06-demo-admin-token"}:
                self.send_json(401, {"error": {"code": "UNAUTHORIZED", "message": "Bearer authorization is required"}})
            else:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length))
                    required = {"attachment_type", "filename", "content_type", "size_bytes", "storage_key"}
                    if not isinstance(payload, dict) or not required <= set(payload):
                        raise ValueError("invalid attachment")
                except (ValueError, json.JSONDecodeError):
                    self.send_json(400, {"error": {"code": "REQUEST_BODY_INVALID", "message": "invalid attachment"}})
                else:
                    self.send_json(200, {"case_id": case_id, "attachment": {"attachment_id": "00000000-0000-4000-8000-000000000001", "attachment_type": payload["attachment_type"], "filename": payload["filename"], "content_type": payload["content_type"], "size_bytes": payload["size_bytes"]}})
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
