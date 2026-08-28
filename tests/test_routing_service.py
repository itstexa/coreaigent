"""Falsification tests for F-05's deterministic routing boundary."""

import ast
import sys
import unittest
from pathlib import Path


WORKFLOW = Path(__file__).parents[1] / "services" / "workflow"
sys.path.insert(0, str(WORKFLOW))

from routing import RoutingRejected, normalize_notification_output, notification_payload, select_route, evaluate_routing  # noqa: E402


TAXONOMY = {
    "taxonomyVersion": "test-v1",
    "departments": [
        {"id": "imar", "label": "İmar Müdürlüğü", "active": True},
        {"id": "diger", "label": "Diğer", "active": True},
    ],
    "units": [
        {"id": "ruhsat", "label": "Ruhsat Birimi", "departmentId": "imar", "active": True},
        {"id": "siniflandirilmamis", "label": "Sınıflandırılamayan", "departmentId": "diger", "active": True},
    ],
}


class RoutingSelectionTests(unittest.TestCase):
    def test_low_confidence_needs_review_without_changing_prediction(self):
        result = evaluate_routing("u1", confidence=0.79, threshold=0.80)
        self.assertTrue(result["needs_review"])
        self.assertEqual(result["predicted_unit_id"], "u1")

    def test_final_accepted_unit_is_ground_truth(self):
        self.assertTrue(evaluate_routing("u1", "u1", 0.9)["routing_correct"])
        self.assertFalse(evaluate_routing("u1", "u2", 0.9)["routing_correct"])

    def test_complete_draft_routes_to_active_classified_chain(self):
        route = select_route(TAXONOMY, classification_status="classified", completion_status="complete", result_status="draft_ready", department_id="imar", unit_id="ruhsat")
        self.assertEqual(route, {"route_kind": "classified", "department_id": "imar", "unit_id": "ruhsat", "taxonomy_version": "test-v1"})

    def test_review_required_routes_to_authoritative_fallback_not_classified_unit(self):
        route = select_route(TAXONOMY, classification_status="classified", completion_status="complete", result_status="review_required", department_id="imar", unit_id="ruhsat")
        self.assertEqual(route["route_kind"], "fallback")
        self.assertEqual((route["department_id"], route["unit_id"]), ("diger", "siniflandirilmamis"))

    def test_unrequested_complete_case_routes_to_fallback(self):
        route = select_route(TAXONOMY, classification_status="classified", completion_status="complete", result_status="not_requested", department_id="imar", unit_id="ruhsat")
        self.assertEqual((route["route_kind"], route["unit_id"]), ("fallback", "siniflandirilmamis"))

    def test_needs_review_does_not_silently_route_to_fallback(self):
        with self.assertRaisesRegex(RoutingRejected, "CLASSIFICATION_NOT_ROUTEABLE"):
            select_route(TAXONOMY, classification_status="needs_review", completion_status="complete", result_status="draft_ready", department_id="imar", unit_id="ruhsat")

    def test_incomplete_case_does_not_create_a_route(self):
        with self.assertRaisesRegex(RoutingRejected, "CASE_NOT_COMPLETE"):
            select_route(TAXONOMY, classification_status="classified", completion_status="missing_information", result_status="draft_ready", department_id="imar", unit_id="ruhsat")

    def test_inactive_classified_unit_is_rejected(self):
        taxonomy = {**TAXONOMY, "units": [{**TAXONOMY["units"][0], "active": False}, TAXONOMY["units"][1]]}
        with self.assertRaisesRegex(RoutingRejected, "ROUTING_TARGET_INACTIVE"):
            select_route(taxonomy, classification_status="classified", completion_status="complete", result_status="draft_ready", department_id="imar", unit_id="ruhsat")

    def test_inactive_fallback_unit_is_rejected(self):
        taxonomy = {**TAXONOMY, "units": [TAXONOMY["units"][0], {**TAXONOMY["units"][1], "active": False}]}
        with self.assertRaisesRegex(RoutingRejected, "ROUTING_TARGET_INACTIVE"):
            select_route(taxonomy, classification_status="classified", completion_status="complete", result_status="review_required", department_id="imar", unit_id="ruhsat")


class NotificationProjectionTests(unittest.TestCase):
    def test_structured_notification_recovery_keeps_only_valid_title_and_body(self):
        recovered = normalize_notification_output({
            "title": "Yeni başvuru yönlendirildi",
            "body": "Başvurunun incelenmesi için işlem yapılması gerekmektedir.",
            "draft_text": "Modelin gereksiz alanı",
            "validated_fields": {"tckn": {"value": "10000000146"}},
        })
        self.assertEqual(recovered, {
            "title": "Yeni başvuru yönlendirildi",
            "body": "Başvurunun incelenmesi için işlem yapılması gerekmektedir.",
        })

    def test_structured_notification_recovery_rejects_missing_or_invalid_fields(self):
        with self.assertRaisesRegex(ValueError, "title and body"):
            normalize_notification_output({"title": "Başlık", "draft_text": "Metin"})
        with self.assertRaisesRegex(ValueError, "bounds"):
            normalize_notification_output({"title": "Başlık", "body": "x" * 4001})

    def test_applicant_payload_is_process_only_and_has_no_internal_context(self):
        payload = notification_payload("applicant", "case-123", "Başvurunuz ilgili birime yönlendirilmiştir.", operational_context={"validated_fields": {"tckn": "x"}, "draft_text": "internal"})
        self.assertEqual(payload, {"audience": "applicant", "case_id": "case-123", "title": "Başvurunuz işleme alındı", "body": "Başvurunuz ilgili birime yönlendirilmiştir.", "email_placeholder": None})

    def test_target_payload_keeps_only_authorized_operational_context(self):
        payload = notification_payload("target_unit", "case-123", "Yeni ruhsat başvurusu bulunmaktadır.", operational_context={"request_type_id": "ruhsat-basvurusu", "validated_fields": {"business_name": "Örnek"}, "draft_text": "Taslak"})
        self.assertEqual(payload["audience"], "target_unit")
        self.assertEqual(payload["case_context"]["request_type_id"], "ruhsat-basvurusu")
        self.assertNotIn("email", payload["case_context"])

    def test_unknown_audience_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "audience"):
            notification_payload("operator", "case-123", "x")

    def test_blank_model_text_is_rejected_and_cannot_be_published(self):
        with self.assertRaisesRegex(ValueError, "body"):
            notification_payload("applicant", "case-123", "")


class WorkerLockingClauseTests(unittest.TestCase):
    """A worker that swallows psycopg errors cannot report broken SQL itself.

    PostgreSQL refuses `FOR UPDATE` on the nullable side of an outer join, so a
    reconciliation scan that omits `OF <relations>` fails on every poll while the
    lane looks merely idle.  The parser concatenates the adjacent literals a
    query is built from, so each statement is one constant here.
    """

    def statements(self):
        for name in ("routing_worker.py", "orchestrator_worker.py", "worker.py"):
            tree = ast.parse((WORKFLOW / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    yield name, " ".join(node.value.split())

    def test_every_outer_joined_claim_locks_named_relations_only(self):
        checked = 0
        for name, sql in self.statements():
            if "FOR UPDATE" not in sql.upper():
                continue
            checked += 1
            if "LEFT JOIN" in sql.upper() or "RIGHT JOIN" in sql.upper():
                self.assertRegex(sql.upper(), r"FOR UPDATE OF [A-Z_]+", f"{name}: {sql[:120]}")
        self.assertGreaterEqual(checked, 4)


if __name__ == "__main__":
    unittest.main()
