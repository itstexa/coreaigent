"""ATDD tests for US-102 Jamba inference behavior.

These tests inject only the model-loader boundary. HTTP parsing, validation,
readiness, singleton lifecycle, locking, and error mapping remain real code.
"""

import json
import threading
import time
import unittest

from unittest.mock import patch

from fastapi.testclient import TestClient

from services.llm.app import (
    MODEL_ID,
    PROMPT_CONTRACT_HASH,
    PROMPT_CONTRACT_VERSION,
    RuntimeConfig,
    build_prose_admin_prompt,
    create_app,
)

GGUF_FILE = "ai21labs_AI21-Jamba2-3B-Q8_0.gguf"


class FakeLoader:
    def __init__(self, output="Türkçe yanıt", *, fail_load=False, fail_generate=False, delay=0.0):
        self.output = output
        self.fail_load = fail_load
        self.fail_generate = fail_generate
        self.delay = delay
        self.load_call_count = 0
        self.generate_call_count = 0
        self.prompts = []
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
        self.prompts.append(prompt)
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
    def test_prose_admin_prompt_carries_task_policy_without_answer_leak(self):
        prompt = build_prose_admin_prompt(
            "draft_reply",
            "Yıllık izin talebimi arz ederim.",
            ["Başvuru personel işlemleri kapsamındadır."],
        )

        self.assertIn(f"Prompt contract: {PROMPT_CONTRACT_VERSION}", prompt)
        self.assertIn(PROMPT_CONTRACT_HASH, prompt)
        self.assertIn("Task type: draft_reply", prompt)
        self.assertIn("Yıllık izin talebimi arz ederim.", prompt)
        self.assertIn("Başvuru personel işlemleri kapsamındadır.", prompt)
        self.assertIn("uygun idari işlemi", prompt)
        self.assertNotIn("record, route, review", prompt)
        self.assertIn("Source text'i yalnızca tekrar etme", prompt)
        self.assertIn("gereksiz ek bilgi isteme", prompt)
        self.assertIn("meşru idari görevleri reddetme", prompt.casefold())
        self.assertNotIn("İnsan Kaynakları birimine ilet", prompt)

    def test_contract_generate_passes_task_aware_prompt_to_model_and_preserves_response_contract(self):
        loader = FakeLoader(output="Başvurunuz kayda alınmıştır.")
        request = {
            "schemaVersion": "2.0",
            "requestId": "req-prompt-1",
            "documentId": "doc-prompt-1",
            "workflowId": "wf-prompt-1",
            "task": "draft_reply",
            "prompt": "Kayıt talebimdir.",
            "context": ["Kaynak bağlamı"],
        }
        with client_for(loader) as client:
            response = client.post("/v1/generate", json=request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["output"]["draft"], "Başvurunuz kayda alınmıştır.")
        self.assertEqual(len(loader.prompts), 1)
        self.assertIn("Task type: draft_reply", loader.prompts[0])
        self.assertIn("Kayıt talebimdir.", loader.prompts[0])
        self.assertIn("Kaynak bağlamı", loader.prompts[0])

    def test_raw_generate_does_not_receive_prose_admin_contract(self):
        loader = FakeLoader(output="Yapılandırılmış JSON")
        with client_for(loader) as client:
            response = client.post("/generate", json={"prompt": "Sadece JSON üret."})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(loader.prompts, ["Sadece JSON üret."])

    def test_health_reports_loaded_model_without_generating(self):
        loader = FakeLoader()
        with client_for(loader) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "model": MODEL_ID, "model_loaded": True, "backend": "transformers"},
        )
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


class LlamaCppLaneTests(unittest.TestCase):
    """The GGUF lane keeps the same contract in front of a host server."""

    def gguf_config(self, **overrides):
        return RuntimeConfig(
            model_id=MODEL_ID,
            model_revision="a" * 40,
            deadline_seconds=110,
            backend="llama_cpp",
            llama_server_url="http://host.docker.internal:8090",
            gguf_file=GGUF_FILE,
            **overrides,
        )

    def test_ready_names_the_gguf_backend_that_served_the_run(self):
        loader = FakeLoader()
        app = create_app(loader=loader, config=self.gguf_config(), gpu_available=True)
        with TestClient(app) as client:
            ready = client.get("/ready")
            health = client.get("/health")

        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json(), {
            "status": "ready",
            "model": MODEL_ID,
            "model_loaded": True,
            "backend": "llama_cpp",
        })
        self.assertEqual(health.json()["backend"], "llama_cpp")

    def test_unreachable_host_server_is_not_ready_and_reattaches_when_it_returns(self):
        loader = FakeLoader()
        reachable = {"value": False}
        with patch("services.llm.app._llama_server_reachable", lambda config: reachable["value"]),                 patch("services.llm.app.UPSTREAM_RETRY_INTERVAL", 0.0):
            with TestClient(create_app(loader=loader, config=self.gguf_config())) as client:
                stopped = client.get("/ready")
                reachable["value"] = True
                restarted = client.get("/ready")
                answer = client.post("/generate", json={"prompt": "Hazır mısın?"})

        self.assertEqual(stopped.status_code, 503)
        # An absent host server is not an absent local GPU.
        self.assertEqual(stopped.json()["error"]["code"], "model_not_ready")
        self.assertEqual(restarted.status_code, 200)
        self.assertEqual(answer.status_code, 200)
        self.assertEqual(loader.load_call_count, 1)

    def test_a_host_server_that_stops_serving_the_pinned_model_flips_readiness_back(self):
        loader = FakeLoader()
        with patch("services.llm.app._llama_server_reachable", lambda config: True),                 patch("services.llm.app.UPSTREAM_RETRY_INTERVAL", 0.0):
            with TestClient(create_app(loader=loader, config=self.gguf_config())) as client:
                serving = client.get("/ready")
                # The process still answers, but it no longer serves the pinned
                # artifact, so re-attaching must fail instead of succeeding.
                loader.healthy = lambda: False
                loader.fail_load = True
                stopped = client.get("/ready")
                refused = client.post("/generate", json={"prompt": "Hazır mısın?"})

        self.assertEqual(serving.status_code, 200)
        self.assertEqual(stopped.status_code, 503)
        self.assertEqual(stopped.json()["error"]["code"], "model_not_ready")
        self.assertEqual(refused.status_code, 503)
        self.assertEqual(loader.generate_call_count, 0)

    def test_the_cuda_lane_is_never_probed_again_after_a_failed_load(self):
        loader = FakeLoader(fail_load=True)
        with patch("services.llm.app._gpu_available", lambda: True),                 patch("services.llm.app.UPSTREAM_RETRY_INTERVAL", 0.0):
            config = RuntimeConfig(model_id=MODEL_ID, model_revision="a" * 40)
            with TestClient(create_app(loader=loader, config=config)) as client:
                for _ in range(3):
                    self.assertEqual(client.get("/ready").status_code, 503)

        self.assertEqual(loader.load_call_count, 1)


if __name__ == "__main__":
    unittest.main()
