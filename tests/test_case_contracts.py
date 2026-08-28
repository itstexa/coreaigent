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
            ("workflow", "POST", "/v1/drafts"),
            ("validation", "PATCH", "/cases/{case_id}/supplemental-information"),
            ("workflow", "GET", "/cases"),
            ("workflow", "POST", "/cases/{case_id}/correspondence"),
            ("workflow", "GET", "/cases/{case_id}/correspondence"),
            ("workflow", "GET", "/cases/{case_id}/routing"),
            ("workflow", "GET", "/cases/{case_id}/document"),
            ("workflow", "GET", "/cases/{case_id}/action-log"),
            ("workflow", "GET", "/cases/{case_id}/training-export"),
            ("workflow", "GET", "/cases/{case_id}/history"),
            ("workflow", "POST", "/cases/{case_id}/resolution-mark"),
            ("workflow", "GET", "/cases/{case_id}/attachments"),
            ("workflow", "POST", "/cases/{case_id}/attachments"),
            ("workflow", "PATCH", "/cases/{case_id}/edit"),
            ("workflow", "GET", "/cases/{case_id}/revisions"),
            ("workflow", "GET", "/cases/{case_id}/priority"),
            ("workflow", "POST", "/cases/{case_id}/priority-override"),
            ("workflow", "GET", "/cases/{case_id}/routing-evaluation"),
            ("workflow", "POST", "/cases/{case_id}/routing-feedback"),
            ("workflow", "GET", "/routing-evaluation"),
            ("workflow", "GET", "/personnel-dashboard"),
            ("workflow", "POST", "/v1/normalize"),
            ("workflow", "GET", "/cases/{case_id}/abuse"),
            ("workflow", "POST", "/cases/{case_id}/abuse-override"),
            ("workflow", "GET", "/moderation-trends"),
            ("workflow", "GET", "/cases/{case_id}"),
            ("workflow", "POST", "/cases/{case_id}/review-completion"),
        })
        for item in self.manifest["additionalEndpoints"]:
            self.assertIn(item["response"], self.schemas)
            if item["method"] != "GET":
                self.assertIn(item["request"], self.schemas)

    def test_action_log_contract_is_strict_and_append_only_shaped(self):
        schema = self.schemas["case-action-log-result"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), {"case_id", "events"})
        event = schema["$defs"]["action_event"]
        self.assertFalse(event["additionalProperties"])
        self.assertEqual(set(event["required"]), {"event_id", "action_type", "actor", "occurred_at", "details"})
        self.assertEqual(set(event["properties"]["action_type"]["enum"]), {
            "state_change", "assignment", "petition_edit", "attachment_change", "spam_decision", "view", "download",
        })

    def test_training_export_contract_cannot_carry_original_metadata(self):
        schema = self.schemas["case-training-export"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), {"case_id", "document_id", "text", "redactions"})
        self.assertNotIn("original_text", schema["properties"])

    def test_history_and_resolution_contracts_are_strict_and_reader_scoped(self):
        history = self.schemas["case-history-result"]
        self.assertFalse(history["additionalProperties"])
        self.assertEqual(set(history["required"]), {"case_id", "resolved", "resolved_by", "similar_cases"})
        similar = history["$defs"]["similar_case"]
        self.assertFalse(similar["additionalProperties"])
        self.assertEqual(set(similar["properties"]["signals"]["items"]["enum"]), {"text", "classification", "location", "time"})
        mark = self.schemas["case-resolution-mark-result"]
        self.assertFalse(mark["additionalProperties"])
        self.assertEqual(mark["properties"]["resolved"], {"const": True})

    def test_attachment_contract_publishes_demo_limits_and_non_authoritative_suggestions(self):
        request = self.schemas["case-attachment-add-request"]
        self.assertFalse(request["additionalProperties"])
        self.assertEqual(request["properties"]["size_bytes"]["maximum"], 10 * 1024 * 1024)
        self.assertEqual(set(request["properties"]["content_type"]["enum"]), {
            "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "image/jpeg", "image/png",
        })
        result = self.schemas["case-attachments-result"]
        self.assertFalse(result["additionalProperties"])
        self.assertEqual(result["$defs"]["suggestion"]["properties"]["authoritative"], {"const": False})

    def test_abuse_contract_is_bounded_and_override_requires_reason(self):
        result = self.schemas["case-abuse-result"]
        self.assertFalse(result["additionalProperties"])
        self.assertEqual(result["properties"]["risk_score"]["minimum"], 0)
        self.assertEqual(result["properties"]["risk_score"]["maximum"], 1)
        self.assertEqual(result["properties"]["detected_signals"]["items"]["enum"], ["duplicate", "burst", "bot_repeat", "profanity", "threat", "harassment"])
        request = self.schemas["case-abuse-override-request"]
        self.assertEqual(set(request["required"]), {"flagged", "reason"})
        self.assertFalse(request["additionalProperties"])

    def test_abuse_trend_contract_is_bounded_and_privacy_shaped(self):
        schema = self.schemas["case-abuse-trend-result"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), {"status", "scope", "period_days", "points"})
        self.assertEqual(schema["properties"]["period_days"]["enum"], [7, 30, 90])
        point = schema["properties"]["points"]["items"]
        self.assertGreaterEqual(point["properties"]["total"]["minimum"], 5)
        self.assertEqual(point["properties"]["rate"]["minimum"], 0)
        self.assertEqual(point["properties"]["rate"]["maximum"], 1)

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
