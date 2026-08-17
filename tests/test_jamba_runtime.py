"""ATDD tests for US-103 CUDA/SSM and Compose runtime wiring."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path

from services.llm.app import MODEL_ID, RuntimeConfig


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
        self.assertEqual(base.hf_cache_dir, "/var/cache/huggingface/hub")

        self.assertIsNone(replace(base, max_new_tokens=1).validation_error())
        self.assertIsNone(replace(base, max_new_tokens=512).validation_error())
        self.assertIsNotNone(replace(base, max_new_tokens=0).validation_error())
        self.assertIsNotNone(replace(base, max_new_tokens=513).validation_error())

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
        self.assertIn(llm["gpus"], ("all", [{"count": -1}]))
        self.assertTrue(any(volume["target"] == "/var/cache/huggingface" for volume in llm["volumes"]))
        self.assertIn("llm-hf-cache", resolved["volumes"])

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
