"""Deterministic, contract-shaped HTTP mocks; intentionally stdlib-only."""
import json
import os
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SERVICE = os.environ.get("MOCK_SERVICE", "ocr")
MANIFEST = json.loads(Path("/contracts/http/manifest.json").read_text(encoding="utf-8"))["services"]
SCENARIOS = json.loads(Path("/scenarios/golden-scenarios.json").read_text(encoding="utf-8"))["scenarios"]
BY_ID = {item["id"]: item for item in SCENARIOS}


def scenario(payload):
    key = payload.get("scenarioId") or payload.get("documentId", "").removeprefix("doc-")
    return BY_ID.get(key)


def tracing(payload):
    return {
        "schemaVersion": "1.0",
        "requestId": payload.get("requestId", "unknown-request"),
        "documentId": payload.get("documentId", "unknown-document"),
        "workflowId": payload.get("workflowId") or "wf-" + payload.get("documentId", "unknown-document"),
    }


def result(payload, item):
    trace = tracing(payload)
    if SERVICE == "ocr":
        return trace | {"text": item["text"], "language": "tr", "confidence": 0.91, "pages": 1, "warnings": []}
    if SERVICE == "analysis":
        missing = [] if item["classification"] != "needs_information" else ["required_attachment"]
        return trace | {"documentType": item["documentType"], "classification": item["classification"], "extractedFields": {"scenario": item["id"]}, "missingFields": missing, "summary": item["title"]}
    if SERVICE == "rag":
        results = [] if not item["retrieval"] else [{"id": "regulation-" + item["id"], "title": "İlgili kamu mevzuatı", "excerpt": item["title"], "score": 0.9}]
        return trace | {"results": results, "searchedAt": "2026-01-01T00:00:00Z"}
    if SERVICE == "llm":
        return trace | {"output": {"draft": item["draft"], "department": item["department"], "confidence": 0.9}, "model": "mock-deterministic-v1"}
    steps = [{"service": name, "status": "completed" if item["status"] == "completed" or name == "workflow" else "skipped", "timestamp": "2026-01-01T00:00:00Z"} for name in ("ocr", "analysis", "rag", "llm", "workflow")]
    return trace | {"status": item["status"], "documentType": item["documentType"], "department": item["department"], "draft": item["draft"], "steps": steps, "error": None}


def request(service, payload):
    boundary = MANIFEST[service]
    req = urllib.request.Request("http://" + service + ":8080" + boundary["path"], data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read())


def workflow_result(payload, item):
    ocr = request("ocr", payload)
    analysis = request("analysis", ocr)
    trace = {key: analysis[key] for key in ("schemaVersion", "requestId", "documentId", "workflowId")}
    rag = request("rag", trace | {"query": analysis["summary"] or item["title"], "documentType": analysis["documentType"]})
    llm = request("llm", trace | {"task": "draft_reply", "prompt": payload["content"] or item["text"], "context": [entry["excerpt"] for entry in rag["results"]]})
    steps = [{"service": name, "status": "completed", "timestamp": "2026-01-01T00:00:00Z"} for name in ("ocr", "analysis", "rag", "llm", "workflow")]
    return trace | {"status": item["status"], "documentType": analysis["documentType"], "department": llm["output"]["department"], "draft": llm["output"]["draft"], "steps": steps, "error": None}


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

    def send_json(self, status, body):
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-CoreAIgent-Implementation", "mock")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path in ("/health", "/ready"):
            self.send_json(200, {"status": "ready", "service": SERVICE, "implementation": "mock"})
        else:
            self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        expected = MANIFEST[SERVICE]["path"]
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            payload = {}
        item = scenario(payload)
        schema = json.loads(Path("/contracts/schemas/" + MANIFEST[SERVICE]["request"] + ".schema.json").read_text(encoding="utf-8"))
        if self.path != expected or not matches(schema, payload) or not item:
            error = {"schemaVersion": "1.0", "requestId": payload.get("requestId", "unknown-request"), "workflowId": payload.get("workflowId"), "documentId": payload.get("documentId"), "service": SERVICE, "timestamp": "2026-01-01T00:00:00Z", "category": "validation", "message": "Invalid request, unknown scenario, or endpoint", "retryable": False}
            print(json.dumps({"timestamp": error["timestamp"], "requestId": error["requestId"], "workflowId": error["workflowId"], "documentId": error["documentId"], "service": SERVICE, "errorCategory": "validation"}), flush=True)
            self.send_json(400 if self.path == expected else 404, error)
            return
        try:
            body = workflow_result(payload, item) if SERVICE == "workflow" else result(payload, item)
        except Exception as exc:
            error = {"schemaVersion": "1.0", "requestId": payload["requestId"], "workflowId": payload.get("workflowId") or "wf-" + payload["documentId"], "documentId": payload["documentId"], "service": SERVICE, "timestamp": "2026-01-01T00:00:00Z", "category": "dependency", "message": str(exc), "retryable": True}
            print(json.dumps({"timestamp": error["timestamp"], "requestId": error["requestId"], "workflowId": error["workflowId"], "documentId": error["documentId"], "service": SERVICE, "errorCategory": "dependency"}), flush=True)
            self.send_json(502, error)
            return
        print(json.dumps({"timestamp": "2026-01-01T00:00:00Z", "requestId": payload["requestId"], "workflowId": payload.get("workflowId") or "wf-" + payload["documentId"], "documentId": payload["documentId"], "service": SERVICE, "errorCategory": None}), flush=True)
        self.send_json(200, body)


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
