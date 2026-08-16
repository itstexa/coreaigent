"""HTTP server for the draft-generation service."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .engine import DraftError, generate_draft


def _error_payload(request_id: str, message: str, category: str = "validation") -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schemaVersion": "1.0",
        "requestId": request_id,
        "service": "draft",
        "timestamp": now,
        "category": category,
        "message": message,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_json(self, code: int, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path in ("/health", "/ready"):
            self.send_json(200, {"status": "ok", "service": "draft", "implementation": "rule-based"})
            return
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/draft":
            self.send_json(404, {"error": "not_found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length)) if content_length else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}

        request_id = payload.get("requestId", "unknown-request") if isinstance(payload, dict) else "unknown-request"
        try:
            body = generate_draft(payload)
        except DraftError as exc:
            self.send_json(400, _error_payload(request_id, str(exc), "validation"))
            return
        except Exception as exc:  # pragma: no cover - unexpected runtime errors
            self.send_json(500, _error_payload(request_id, str(exc), "dependency"))
            return

        self.send_json(200, body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
