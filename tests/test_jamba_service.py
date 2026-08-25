"""ATDD tests for US-102 Jamba inference behavior.

These tests inject only the model-loader boundary. HTTP parsing, validation,
readiness, singleton lifecycle, locking, and error mapping remain real code.
"""

import json
import threading
import time
import unittest

from fastapi.testclient import TestClient

from services.llm.app import MODEL_ID, RuntimeConfig, create_app


class FakeLoader:
    def __init__(self, output="Türkçe yanıt", *, fail_load=False, fail_generate=False, delay=0.0):
        self.output = output
        self.fail_load = fail_load
        self.fail_generate = fail_generate
        self.delay = delay
        self.load_call_count = 0
        self.generate_call_count = 0
        self.active_generations = 0
        self.max_active_generations = 0
        self._active_lock = threading.Lock()

    def load(self, config):
        self.load_call_count += 1
        if self.fail_load:
            raise RuntimeError("loader failed")
        return self

    def token_count(self, prompt):
        return len(prompt.split())

    def generate(self, prompt, config):
        with self._active_lock:
            self.active_generations += 1
            self.max_active_generations = max(self.max_active_generations, self.active_generations)
        try:
            self.generate_call_count += 1
            if self.delay:
                time.sleep(self.delay)
            if self.fail_generate:
                raise RuntimeError("generation failed")
            return self.output
        finally:
            with self._active_lock:
                self.active_generations -= 1


def client_for(loader, *, gpu_available=True, **config_overrides):
    config = RuntimeConfig(
        model_id=MODEL_ID,
        model_revision="a" * 40,
        max_new_tokens=256,
        temperature=0.7,
        top_p=0.9,
        deadline_seconds=60,
        **config_overrides,
    )
    return TestClient(create_app(loader=loader, config=config, gpu_available=gpu_available))


class JambaServiceAcceptanceTests(unittest.TestCase):
    def test_health_reports_loaded_model_without_generating(self):
        loader = FakeLoader()
        with client_for(loader) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "model": MODEL_ID, "model_loaded": True})
        self.assertEqual(loader.generate_call_count, 0)

    def test_health_is_live_but_ready_rejects_without_gpu(self):
        loader = FakeLoader()
        with client_for(loader, gpu_available=False) as client:
            health = client.get("/health")
            ready = client.get("/ready")

        self.assertEqual(health.status_code, 200)
        self.assertFalse(health.json()["model_loaded"])
        self.assertEqual(ready.status_code, 503)
        self.assertEqual(ready.json()["error"]["code"], "gpu_unavailable")
        self.assertEqual(loader.load_call_count, 0)

    def test_ready_reports_model_load_failure_without_killing_liveness(self):
        loader = FakeLoader(fail_load=True)
        with client_for(loader) as client:
            health = client.get("/health")
            ready = client.get("/ready")

        self.assertEqual(health.status_code, 200)
        self.assertFalse(health.json()["model_loaded"])
        self.assertEqual(ready.status_code, 503)
        self.assertEqual(ready.json()["error"]["code"], "model_not_ready")
        self.assertEqual(loader.load_call_count, 1)

    def test_generate_returns_turkish_text_and_fixed_model_id(self):
        loader = FakeLoader(output="Başvurunuz incelenmiştir.")
        with client_for(loader) as client:
            response = client.post("/generate", json={"prompt": "Belgeyi Türkçe özetle."})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "model": MODEL_ID,
            "modelRevision": "a" * 40,
            "response": "Başvurunuz incelenmiştir.",
        })
        self.assertEqual(loader.generate_call_count, 1)

    def test_contract_generate_returns_contract_shaped_trace_and_safe_department(self):
        loader = FakeLoader(output="Resmî yanıt taslağı")
        request = {
            "schemaVersion": "2.0",
            "requestId": "req-1",
            "documentId": "doc-1",
            "workflowId": "wf-1",
            "task": "draft_reply",
            "prompt": "Başvuruyu yanıtla.",
            "context": ["Mevzuat özeti"],
        }
        with client_for(loader) as client:
            response = client.post("/v1/generate", json=request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "schemaVersion": "2.0",
            "requestId": "req-1",
            "documentId": "doc-1",
            "workflowId": "wf-1",
            "output": {"draft": "Resmî yanıt taslağı", "department": "manual_review", "confidence": 0.0},
            "model": MODEL_ID,
        })
        self.assertEqual(loader.generate_call_count, 1)

    def test_contract_generate_rejects_invalid_payload_with_standard_error(self):
        loader = FakeLoader()
        with client_for(loader) as client:
            response = client.post("/v1/generate", json={})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["service"], "llm")
        self.assertEqual(response.json()["category"], "validation")
        self.assertFalse(response.json()["retryable"])
        self.assertEqual(loader.generate_call_count, 0)

    def test_contract_error_sanitizes_invalid_trace_types(self):
        loader = FakeLoader()
        with client_for(loader) as client:
            response = client.post("/v1/generate", json={"documentId": 42, "workflowId": []})

        self.assertEqual(response.status_code, 400)
        self.assertIsNone(response.json()["documentId"])
        self.assertIsNone(response.json()["workflowId"])

    def test_contract_generate_reports_not_ready_with_retryable_standard_error(self):
        loader = FakeLoader()
        request = {
            "schemaVersion": "2.0",
            "requestId": "req-1",
            "documentId": "doc-1",
            "workflowId": "wf-1",
            "task": "summarize",
            "prompt": "Özetle.",
        }
        with client_for(loader, gpu_available=False) as client:
            response = client.post("/v1/generate", json=request)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["category"], "dependency")
        self.assertTrue(response.json()["retryable"])
        self.assertEqual(loader.generate_call_count, 0)

    def test_generate_rejects_malformed_json_with_400(self):
        loader = FakeLoader()
        with client_for(loader) as client:
            response = client.post("/generate", content=b"{not-json", headers={"content-type": "application/json"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "malformed_json")
        self.assertEqual(loader.generate_call_count, 0)

    def test_generate_rejects_missing_empty_and_wrong_type_prompts_with_422(self):
        loader = FakeLoader()
        with client_for(loader) as client:
            responses = [
                client.post("/generate", json={}),
                client.post("/generate", json={"prompt": ""}),
                client.post("/generate", json={"prompt": "   \n\t"}),
                client.post("/generate", json={"prompt": None}),
                client.post("/generate", json={"prompt": 123}),
            ]

        self.assertEqual([response.status_code for response in responses], [422, 422, 422, 422, 422])
        self.assertEqual([response.json()["error"]["code"] for response in responses], [
            "empty_prompt", "empty_prompt", "empty_prompt", "invalid_prompt_type", "invalid_prompt_type",
        ])
        self.assertEqual(loader.generate_call_count, 0)

    def test_prompt_token_limit_accepts_8191_and_8192_but_rejects_8193(self):
        loader = FakeLoader()
        with client_for(loader) as client:
            below = client.post("/generate", json={"prompt": "kelime " * 8191})
            exact = client.post("/generate", json={"prompt": "kelime " * 8192})
            above = client.post("/generate", json={"prompt": "kelime " * 8193})

        self.assertEqual(below.status_code, 200)
        self.assertEqual(exact.status_code, 200)
        self.assertEqual(above.status_code, 422)
        self.assertEqual(above.json()["error"]["code"], "prompt_too_long")
        self.assertEqual(loader.generate_call_count, 2)

    def test_generate_returns_503_when_model_is_not_ready(self):
        loader = FakeLoader()
        with client_for(loader, gpu_available=False) as client:
            response = client.post("/generate", json={"prompt": "İnference hazır mı?"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "gpu_unavailable")
        self.assertEqual(loader.generate_call_count, 0)

    def test_generation_failure_returns_500_json_error(self):
        loader = FakeLoader(fail_generate=True)
        with client_for(loader) as client:
            response = client.post("/generate", json={"prompt": "Üretim yap."})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "generation_failed")

    def test_loader_is_called_once_and_generation_is_serialized(self):
        loader = FakeLoader(delay=0.02)
        with client_for(loader) as client:
            responses = []

            def request():
                responses.append(client.post("/generate", json={"prompt": "Sıralı istek"}))

            threads = [threading.Thread(target=request) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(loader.load_call_count, 1)
        self.assertEqual(loader.generate_call_count, 2)
        self.assertEqual(loader.max_active_generations, 1)
        self.assertEqual([response.status_code for response in responses], [200, 200])


if __name__ == "__main__":
    unittest.main()
