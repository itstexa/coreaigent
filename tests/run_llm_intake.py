"""Real local Jamba readiness and provenance smoke check."""

import json
import urllib.request


BASE_URL = "http://llm:8080"
MODEL_ID = "ai21labs/AI21-Jamba2-3B"


def get(path):
    with urllib.request.urlopen(BASE_URL + path, timeout=30) as response:
        assert response.status == 200
        return json.load(response)


def post(path, payload):
    request = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        assert response.status == 200
        return json.load(response)


ready = get("/ready")
assert ready["status"] == "ready" and ready["model_loaded"] is True, ready
assert ready["model"] == MODEL_ID, ready
# The lane must name the real backend that served this run.
assert ready["backend"] in {"transformers", "llama_cpp"}, ready
assert set(ready) == {"status", "model", "model_loaded", "backend"}, ready
result = post("/generate", {"prompt": "Yalnızca tamam yaz."})
assert result["model"] == MODEL_ID, result
assert len(result["modelRevision"]) == 40 and all(char in "0123456789abcdef" for char in result["modelRevision"]), result
assert isinstance(result["response"], str) and result["response"].strip(), result
print("F-08 real local Jamba intake: passed")
