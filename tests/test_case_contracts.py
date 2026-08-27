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
            ("workflow", "GET", "/cases"),
            ("workflow", "POST", "/cases/{case_id}/correspondence"),
            ("workflow", "GET", "/cases/{case_id}/correspondence"),
            ("workflow", "GET", "/cases/{case_id}/routing"),
            ("workflow", "GET", "/cases/{case_id}/document"),
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

    def test_case_list_is_a_strict_admin_only_projection(self):
        schema = self.schemas["case-list-result"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), {"total", "limit", "offset", "cases"})
        self.assertEqual(schema["properties"]["limit"]["maximum"], 100)
        item = schema["$defs"]["case_list_item"]
        self.assertFalse(item["additionalProperties"])
        self.assertEqual(set(item["required"]), set(item["properties"]))

    def test_case_list_never_carries_correspondence_or_notification_content(self):
        """The queue names a case; it must not become a bulk content export.

        Draft text, validated field values and notification payloads are the
        per-case admin read, gated one case at a time.  A list that repeated
        them would hand every applicant's data over in a single request.
        """
        item = self.schemas["case-list-result"]["$defs"]["case_list_item"]
        for leaked in ("draft_text", "document_summary", "validated_fields", "applicant_notifications", "target_unit_notification", "operational_context"):
            self.assertNotIn(leaked, item["properties"])

    def test_case_list_admits_a_case_that_never_reached_validation(self):
        """A needs_review case has a projection but no F-03 row.

        Its request type, unit and applicant are unknown, so the queue row must
        allow nulls there -- otherwise the operator's list silently omits
        exactly the cases that need a human.
        """
        properties = self.schemas["case-list-result"]["$defs"]["case_list_item"]["properties"]
        for nullable in ("document_id", "request_type_id", "unit_id", "applicant_name", "created_at", "language"):
            self.assertIn("null", properties[nullable]["type"])
        self.assertIn(None, properties["validation_status"]["enum"])
        self.assertIn(None, properties["classification_status"]["enum"])


if __name__ == "__main__":
    unittest.main()
