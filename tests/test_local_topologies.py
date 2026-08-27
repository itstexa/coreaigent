"""F-08 local Compose topology contract tests."""

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "scripts" / "local-topologies.json"


class LocalTopologyTests(unittest.TestCase):
    def setUp(self):
        self.topologies = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["topologies"]

    def test_real_local_closures_are_complete_and_ordered(self):
        expected = {
            "ocr": ["compose.yaml", "compose.ocr.yaml"],
            "classification": ["compose.yaml", "compose.ocr.yaml", "compose.classification.yaml"],
            "validation": ["compose.yaml", "compose.ocr.yaml", "compose.classification.yaml", "compose.llm.yaml", "compose.validation.yaml", "compose.validation.jamba.yaml"],
            "workflow": ["compose.yaml", "compose.ocr.yaml", "compose.classification.yaml", "compose.llm.yaml", "compose.validation.yaml", "compose.validation.jamba.yaml", "compose.workflow.yaml"],
            "llm": ["compose.yaml", "compose.llm.yaml"],
            # GGUF closures serve the same pinned model through the host
            # llama.cpp Vulkan server on hosts without an NVIDIA GPU.
            "llm-gguf": ["compose.yaml", "compose.llm.gguf.yaml"],
            "workflow-gguf": ["compose.yaml", "compose.ocr.yaml", "compose.classification.yaml", "compose.llm.gguf.yaml", "compose.validation.yaml", "compose.validation.jamba.yaml", "compose.workflow.yaml"],
        }
        self.assertEqual(set(self.topologies), set(expected))
        for service, files in expected.items():
            with self.subTest(service=service):
                topology = self.topologies[service]
                self.assertEqual(topology["compose_files"], files)
                self.assertEqual(topology["verification_kind"], "real_local")
                self.assertEqual(topology["missing_dependencies"], [])
                self.assertTrue(topology["acceptance_runner"])
                for compose_file in files:
                    self.assertTrue((ROOT / compose_file).is_file(), compose_file)

    def test_real_local_services_have_checked_in_dockerfiles(self):
        for service, topology in self.topologies.items():
            with self.subTest(service=service):
                for local_service in topology["local_services"]:
                    self.assertTrue((ROOT / "services" / local_service / "Dockerfile").is_file(), local_service)

    def test_wrapper_uses_registry_and_named_development_runner(self):
        script = (ROOT / "scripts" / "coreaigent.ps1").read_text(encoding="utf-8")
        self.assertIn("local-topologies.json", script)
        self.assertIn("Get-LocalTopology", script)
        self.assertIn("acceptance_runner", script)
        self.assertNotIn('@("--mode", "development", "--local", $Local)', script)
        self.assertIn("A mock cannot be started as a real", script)


if __name__ == "__main__":
    unittest.main()
