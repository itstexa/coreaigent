"""ATDD tests for US-103 CUDA/SSM and Compose runtime wiring."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from services.llm.app import DEADLINE_LIMIT, MODEL_ID, RuntimeConfig


class JambaRuntimeAcceptanceTests(unittest.TestCase):
    def test_runtime_declares_accelerate_for_device_map_loading(self):
        requirements = Path("services/llm/requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(requirements, r"(?m)^accelerate==[0-9]+\.[0-9]+\.[0-9]+$")

    def test_runtime_image_contains_compiler_for_triton_ssm_kernel_jit(self):
        dockerfile = Path("services/llm/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("gcc", dockerfile)

    def test_reference_runtime_configuration_boundaries(self):
        base = RuntimeConfig(model_revision="a" * 40)
        self.assertIsNone(base.validation_error())
        with patch.dict(os.environ, {"HUGGINGFACE_HUB_CACHE": "/mounted/hf-cache"}):
            self.assertEqual(base.hf_cache_dir, "/mounted/hf-cache")

        self.assertIsNone(replace(base, max_new_tokens=1).validation_error())
        self.assertIsNone(replace(base, max_new_tokens=1799).validation_error())
        self.assertIsNone(replace(base, max_new_tokens=1800).validation_error())
        self.assertIsNotNone(replace(base, max_new_tokens=0).validation_error())
        self.assertIsNotNone(replace(base, max_new_tokens=1801).validation_error())

        self.assertIsNone(replace(base, temperature=0.0).validation_error())
        self.assertIsNone(replace(base, temperature=2.0).validation_error())
        self.assertIsNotNone(replace(base, temperature=-0.0001).validation_error())
        self.assertIsNotNone(replace(base, temperature=2.0001).validation_error())

        self.assertIsNotNone(replace(base, top_p=0.0).validation_error())
        self.assertIsNone(replace(base, top_p=1.0).validation_error())
        self.assertIsNotNone(replace(base, top_p=1.0001).validation_error())

        self.assertIsNone(replace(base, deadline_seconds=5.0).validation_error())
        self.assertIsNone(replace(base, deadline_seconds=120.0).validation_error())
        self.assertIsNotNone(replace(base, deadline_seconds=4.999).validation_error())
        self.assertIsNotNone(replace(base, deadline_seconds=120.001).validation_error())

    def test_gguf_lane_requires_a_pinned_artifact_behind_a_real_server(self):
        base = RuntimeConfig(model_revision="a" * 40)
        self.assertFalse(base.gguf_mode)
        self.assertIsNone(base.validation_error())
        self.assertIsNotNone(replace(base, backend="rocm").validation_error())

        gguf = replace(
            base,
            backend="llama_cpp",
            llama_server_url="http://host.docker.internal:8090/",
            gguf_file="ai21labs_AI21-Jamba2-3B-Q8_0.gguf",
        )
        self.assertTrue(gguf.gguf_mode)
        self.assertIsNone(gguf.validation_error())
        self.assertEqual(gguf.upstream_url, "http://host.docker.internal:8090")

        # A GGUF lane without a reachable URL or a pinned artifact must not
        # start, so it can never quietly serve something else.
        self.assertIsNotNone(replace(gguf, llama_server_url="").validation_error())
        self.assertIsNotNone(replace(gguf, llama_server_url="host.docker.internal:8090").validation_error())
        self.assertIsNotNone(replace(gguf, gguf_file="").validation_error())
        self.assertIsNotNone(replace(gguf, gguf_file="model.safetensors").validation_error())

        # Neither lane may widen the bounded serialized generation budget.
        self.assertIsNone(replace(gguf, deadline_seconds=DEADLINE_LIMIT).validation_error())
        self.assertIsNotNone(replace(gguf, deadline_seconds=DEADLINE_LIMIT + 0.001).validation_error())
        self.assertIsNotNone(replace(base, deadline_seconds=900.0).validation_error())

    def test_gguf_lane_is_read_from_the_environment(self):
        environment = {
            "MODEL_REVISION": "a" * 40,
            "BACKEND": "LLAMA_CPP ",
            "LLAMA_SERVER_URL": " http://host.docker.internal:8090 ",
            "GGUF_FILE": " ai21labs_AI21-Jamba2-3B-Q8_0.gguf ",
        }
        with patch.dict(os.environ, environment):
            config = RuntimeConfig.from_env()
        self.assertTrue(config.gguf_mode)
        self.assertIsNone(config.validation_error())

        with patch.dict(os.environ, {"MODEL_REVISION": "a" * 40}, clear=False):
            for name in ("BACKEND", "LLAMA_SERVER_URL", "GGUF_FILE"):
                os.environ.pop(name, None)
            self.assertFalse(RuntimeConfig.from_env().gguf_mode)

    def test_gguf_image_carries_the_service_without_the_cuda_stack(self):
        dockerfile = Path("services/llm/Dockerfile.gguf").read_text(encoding="utf-8")
        self.assertIn("BACKEND=llama_cpp", dockerfile)
        self.assertIn("must not ship torch", dockerfile)
        # Weights and CUDA kernels belong to the other lane only.
        for absent in ("mamba_ssm", "causal_conv1d", "requirements.txt"):
            self.assertNotIn(absent, dockerfile)

    def test_host_server_script_pins_and_verifies_every_artifact(self):
        script = Path("scripts/jamba-gguf-server.ps1").read_text(encoding="utf-8")
        self.assertIn("0300643b1479bac0eda015f9a00c564217b60856d2cf4c72b0e9fa6b1a5b0133", script)
        self.assertIn("2c624f1d663d2d9e1008d718c3e8d67ae62a19733ddde89ee90872e0c84eb50b", script)
        self.assertIn("Refusing to serve an unpinned artifact", script)
        self.assertIn("02d70acd708332ec4e78e9ceefe116851a307411", script)
        self.assertNotIn("/resolve/main/", script)

    def test_compose_gguf_overlay_serves_the_pinned_model_without_a_gpu(self):
        env = os.environ.copy()
        for name in ("MODEL_ID", "MODEL_REVISION", "LLAMA_SERVER_URL", "GGUF_FILE", "GENERATION_DEADLINE_SECONDS"):
            env.pop(name, None)
        result = subprocess.run(
            [
                "docker", "compose", "-f", "compose.yaml", "-f", "compose.llm.gguf.yaml",
                "config", "--format", "json",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        llm = json.loads(result.stdout)["services"]["llm"]
        self.assertEqual(llm["image"], "coreaigent/llm:jamba-gguf")
        self.assertTrue(llm["build"]["dockerfile"].endswith("Dockerfile.gguf"))
        self.assertNotIn("gpus", llm)

        environment = llm["environment"]
        self.assertEqual(environment["BACKEND"], "llama_cpp")
        self.assertEqual(environment["MODEL_ID"], MODEL_ID)
        self.assertEqual(environment["MODEL_REVISION"], "525c6c8e1d9f5bddedfbdc1dbb0ade2df84230c9")
        self.assertEqual(environment["LLAMA_SERVER_URL"], "http://host.docker.internal:8090")
        self.assertTrue(environment["GGUF_FILE"].endswith(".gguf"))
        self.assertLessEqual(float(environment["GENERATION_DEADLINE_SECONDS"]), DEADLINE_LIMIT)
        # The adapter holds no weights, so it needs no model cache mount.
        self.assertNotIn("volumes", llm)
        # Compose normalizes "host:gateway" to "host=gateway" when it resolves.
        self.assertTrue(
            any(entry.replace("=", ":") == "host.docker.internal:host-gateway" for entry in llm["extra_hosts"]),
            llm["extra_hosts"],
        )

    def test_compose_llm_overlay_reserves_gpu_and_persistent_hf_cache(self):
        env = os.environ.copy()
        env.pop("MODEL_ID", None)
        env.pop("MODEL_REVISION", None)
        result = subprocess.run(
            [
                "docker", "compose", "-f", "compose.yaml", "-f", "compose.llm.yaml",
                "config", "--format", "json",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        resolved = json.loads(result.stdout)
        llm = resolved["services"]["llm"]
        self.assertEqual(llm["image"], "coreaigent/llm:jamba-local")
        self.assertEqual(llm["build"]["context"], str(Path("services/llm").resolve()))
        self.assertIn(llm["gpus"], ("all", [{"count": -1}]))
        cache_mounts = [volume for volume in llm["volumes"] if volume["target"] == "/var/cache/huggingface"]
        self.assertEqual(len(cache_mounts), 1, llm["volumes"])
        # An operator may bind an existing cache through HF_CACHE_DIR; with no
        # override the lane must fall back to the declared named volume.
        if cache_mounts[0]["type"] == "volume":
            self.assertEqual(cache_mounts[0]["source"], "llm-hf-cache")
            self.assertIn("llm-hf-cache", resolved["volumes"])
        else:
            self.assertIn("llm-hf-cache", Path("compose.llm.yaml").read_text(encoding="utf-8"))

    def test_real_overlay_requires_the_pinned_model_identity(self):
        env = os.environ.copy()
        env.pop("MODEL_ID", None)
        env["MODEL_REVISION"] = "a" * 40
        result = subprocess.run(
            ["docker", "compose", "-f", "compose.yaml", "-f", "compose.llm.yaml", "config", "--format", "json"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        llm_environment = json.loads(result.stdout)["services"]["llm"]["environment"]
        self.assertEqual(llm_environment["MODEL_ID"], MODEL_ID)
        self.assertEqual(llm_environment["MODEL_REVISION"], "a" * 40)
        self.assertNotEqual(llm_environment["MODEL_REVISION"], "main")
        self.assertEqual(llm_environment["HF_HOME"], "/var/cache/huggingface")


if __name__ == "__main__":
    unittest.main()
