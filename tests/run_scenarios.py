import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from jsonschema import Draft202012Validator
import validate_contracts

ROOT = Path("/") if Path("/contracts").exists() else Path(__file__).resolve().parents[1]
SCHEMAS = {p.stem.removesuffix(".schema"): json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "contracts/schemas").glob("*.schema.json")}
MANIFEST = json.loads((ROOT / "contracts/http/manifest.json").read_text(encoding="utf-8"))["services"]
SCENARIOS = json.loads((ROOT / "scenarios/golden-scenarios.json").read_text(encoding="utf-8"))["scenarios"]


def valid(name, payload):
    errors = list(Draft202012Validator(SCHEMAS[name]).iter_errors(payload))
    assert not errors, f"{name}: {errors[0].json_path} {errors[0].message}"


def call(service, payload):
    request = urllib.request.Request(
        f"http://{service}:8080{MANIFEST[service]['path']}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read()), response.headers.get("X-CoreAIgent-Implementation")
    except urllib.error.HTTPError as exc:
        raise AssertionError(f"{service} returned HTTP {exc.code}: {exc.read().decode()}") from exc


def error_contract(service):
    request = urllib.request.Request(f"http://{service}:8080{MANIFEST[service]['path']}", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(request, timeout=20)
        raise AssertionError(f"{service} accepted an invalid request")
    except urllib.error.HTTPError as exc:
        assert exc.code == 400
        valid("standard-error", json.loads(exc.read()))


def document(item):
    return {"schemaVersion": "1.0", "requestId": "test-" + item["id"], "documentId": "doc-" + item["id"], "scenarioId": item["id"], "contentType": "text/plain", "content": item["text"], "fileName": None, "source": "test"}


def assert_mock(item, service, payload, local):
    if service == "ocr": assert payload["text"] == item["text"]
    if service == "analysis": assert payload["classification"] == item["classification"]
    if service == "rag": assert bool(payload["results"]) == item["retrieval"]
    if service == "llm": assert payload["output"]["draft"] == item["draft"]
    if service == "workflow":
        assert payload["status"] == item["status"]
        if local != "llm": assert payload["department"] == item["department"]


def run(item, mode, local):
    doc = document(item)
    ocr, ocr_header = call("ocr", doc)
    analysis, analysis_header = call("analysis", ocr)
    trace = {k: analysis[k] for k in ("schemaVersion", "requestId", "documentId", "workflowId")}
    rag, rag_header = call("rag", trace | {"query": analysis["summary"] or item["title"], "documentType": analysis["documentType"]})
    llm, llm_header = call("llm", trace | {"task": "draft_reply", "prompt": item["text"], "context": [r["excerpt"] for r in rag["results"]]})
    workflow, workflow_header = call("workflow", doc)
    responses = {"ocr": (ocr, ocr_header), "analysis": (analysis, analysis_header), "rag": (rag, rag_header), "llm": (llm, llm_header), "workflow": (workflow, workflow_header)}
    for service, (payload, header) in responses.items():
        valid(MANIFEST[service]["response"], payload)
        must_be_mock = mode == "mock" or (mode == "development" and service != local)
        if must_be_mock:
            assert header == "mock", f"{service} is not the expected mock"
            assert_mock(item, service, payload, local)
    if item["retrieval"]:
        assert rag["results"], f"{item['id']}: retrieval expected a result"
    assert workflow["draft"], f"{item['id']}: workflow draft must not be blank"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("mock", "development", "real"), required=True)
    parser.add_argument("--local", choices=tuple(MANIFEST), help="local real service in development mode")
    parser.add_argument("--limit", type=int, default=58)
    args = parser.parse_args()
    if args.mode == "development" and not args.local:
        parser.error("--local is required in development mode")
    validate_contracts.main()
    for service in MANIFEST:
        error_contract(service)
    for item in SCENARIOS[:args.limit]:
        run(item, args.mode, args.local)
    print(f"{min(args.limit, len(SCENARIOS))} {args.mode} scenario(s) passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"scenario test failed: {exc}", file=sys.stderr)
        raise
