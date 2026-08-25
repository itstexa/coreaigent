"""F-09 contract atlas falsification checks."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CaseContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "contracts/http/manifest.json").read_text())
        self.schemas = {path.stem.removesuffix(".schema"): json.loads(path.read_text()) for path in (ROOT / "contracts/schemas").glob("*.schema.json")}

    def test_manifest_lists_every_implemented_case_route_once(self):
        actual = {(item["service"], item["method"], item["path"]) for item in self.manifest["additionalEndpoints"]}
        self.assertEqual(actual, {
            ("validation", "PATCH", "/cases/{case_id}/supplemental-information"),
            ("workflow", "POST", "/cases/{case_id}/correspondence"),
            ("workflow", "GET", "/cases/{case_id}/correspondence"),
            ("workflow", "GET", "/cases/{case_id}/routing"),
            ("workflow", "GET", "/cases/{case_id}"),
            ("workflow", "POST", "/cases/{case_id}/review-completion"),
        })
        for item in self.manifest["additionalEndpoints"]:
            self.assertIn(item["response"], self.schemas)
            if item["method"] != "GET":
                self.assertIn(item["request"], self.schemas)

    def test_correspondence_result_discriminates_lifecycle_branches(self):
        branches = self.schemas["case-correspondence-result"]["oneOf"]
        self.assertEqual(len(branches), 4)
        by_status = {branch["properties"]["generation_status"].get("const", "active"): branch for branch in branches}
        self.assertEqual(set(by_status), {"not_requested", "active", "completed", "failed"})
        self.assertEqual(by_status["active"]["properties"]["generation_status"]["enum"], ["queued", "processing"])
        self.assertEqual(by_status["not_requested"]["properties"]["result"], {"type": "null"})
        self.assertFalse(by_status["failed"]["additionalProperties"])
        self.assertNotIn("draft_text", by_status["failed"]["properties"])

    def test_case_status_keeps_user_and_admin_views_separate_and_strict(self):
        branches = self.schemas["case-status-result"]["oneOf"]
        self.assertEqual(len(branches), 2)
        user_view, admin_view = branches
        self.assertFalse(user_view["additionalProperties"])
        self.assertFalse(admin_view["additionalProperties"])
        self.assertNotIn("operational_context", user_view["properties"])
        self.assertIn("routing", admin_view["required"])
        self.assertIn("target_unit_notification", admin_view["required"])
        self.assertFalse(self.schemas["case-status-result"]["$defs"]["applicant_notice"]["additionalProperties"])

        routing_schema = admin_view["properties"]["routing"]["oneOf"][1]
        self.assertFalse(routing_schema["additionalProperties"])
        self.assertEqual(set(routing_schema["required"]), {"target_department_id", "target_unit_id"})
        self.assertEqual(set(self.schemas["case-status-result"]["$defs"]["operational_context"]["required"]), {
            "validated_fields", "department_id", "unit_id", "request_type_id", "document_summary", "draft_text",
        })


if __name__ == "__main__":
    unittest.main()
