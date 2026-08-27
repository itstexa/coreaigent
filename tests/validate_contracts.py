import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path("/") if Path("/contracts").exists() else Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contracts" / "schemas"


def main():
    manifest = json.loads((ROOT / "contracts/http/manifest.json").read_text(encoding="utf-8"))
    names = {path.stem.removesuffix(".schema") for path in SCHEMAS.glob("*.schema.json")}
    assert manifest["errorResponse"] in names
    for service, boundary in manifest["services"].items():
        assert boundary["request"] in names, f"{service}: request schema missing"
        assert boundary["response"] in names, f"{service}: response schema missing"
        assert boundary["path"].startswith("/v1/")
    seen = set()
    for boundary in manifest.get("additionalEndpoints", []):
        assert boundary["service"] in manifest["services"]
        assert boundary["method"] in {"GET", "POST", "PATCH"}
        # The case collection (GET /cases) is an endpoint on the same resource
        # family as the per-case reads, so it belongs in this list even though it
        # carries no {case_id} segment.
        assert boundary["path"] == "/cases" or boundary["path"].startswith("/cases/{case_id}")
        identity = (boundary["service"], boundary["method"], boundary["path"])
        assert identity not in seen, f"duplicate endpoint: {identity}"
        seen.add(identity)
        if boundary["method"] == "GET":
            assert "request" not in boundary
        else:
            assert boundary["request"] in names
        assert boundary["response"] in names
    for path in SCHEMAS.glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        version = schema.get("properties", {}).get("schemaVersion")
        if version is not None:
            assert version.get("const") in {"2.0", "3.0"} or version.get("enum") == ["2.0", "3.0"], path.name
    scenarios = json.loads((ROOT / "scenarios/golden-scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    assert len(scenarios) == 58, "golden dataset must remain 58 scenarios"
    assert len({s["id"] for s in scenarios}) == 58
    required = {"id", "title", "documentType", "classification", "department", "status", "requiresOcr", "retrieval", "text", "draft"}
    for item in scenarios:
        assert required <= item.keys(), item["id"]
    print("contracts and 58 golden scenarios are valid")


if __name__ == "__main__":
    main()
