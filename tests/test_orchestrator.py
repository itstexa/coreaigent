"""Falsification tests for F-06 state and automatic-start decisions."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "workflow"))

from orchestrator import MAX_F04_START_ATTEMPTS, derive_case_state, next_start_action, project_case  # noqa: E402


class AutomaticStartTests(unittest.TestCase):
    def test_complete_classified_case_without_generation_starts_f04(self):
        self.assertEqual(next_start_action("classified", "complete", None, 0), "start")

    def test_initial_plus_three_retries_is_exactly_four_attempts(self):
        self.assertEqual(MAX_F04_START_ATTEMPTS, 4)
        self.assertEqual(next_start_action("classified", "complete", "failed", 3), "retry")
        self.assertEqual(next_start_action("classified", "complete", "failed", 4), "terminal_failure")
        self.assertEqual(next_start_action("classified", "complete", "failed", 5), "terminal_failure")

    def test_needs_review_and_incomplete_states_never_start_f04(self):
        self.assertEqual(next_start_action("needs_review", "complete", None, 0), "none")
        self.assertEqual(next_start_action("classified", "missing_information", None, 0), "none")
        self.assertEqual(next_start_action("classified", "invalid_information", None, 0), "none")


class StateDerivationTests(unittest.TestCase):
    def test_unclassified_or_not_yet_validated_case_remains_observable(self):
        self.assertEqual(derive_case_state("needs_review", None, None, None, None, {}), "needs_review")
        self.assertEqual(derive_case_state("classified", None, None, None, None, {}), "extracting")

    def test_review_required_never_becomes_completed_automatically(self):
        self.assertEqual(derive_case_state("classified", "complete", "completed", "review_required", "routed", {"applicant": "completed", "target_unit": "completed"}), "needs_review")

    def test_draft_ready_route_with_completed_notifications_completes(self):
        self.assertEqual(derive_case_state("classified", "complete", "completed", "draft_ready", "routed", {"applicant": "completed", "target_unit": "completed"}), "completed")

    def test_notification_failure_is_pending_not_completed(self):
        self.assertEqual(derive_case_state("classified", "complete", "completed", "draft_ready", "routed", {"applicant": "failed", "target_unit": "completed"}), "notification_pending")

    def test_missing_and_invalid_wait_for_user(self):
        self.assertEqual(derive_case_state("classified", "missing_information", None, None, None, {}), "waiting_for_user")
        self.assertEqual(derive_case_state("classified", "invalid_information", None, None, None, {}), "waiting_for_user")


class ProjectionTests(unittest.TestCase):
    def test_user_projection_excludes_internal_and_target_payload(self):
        source = {"case_id": "c", "state": "needs_review", "validation_status": "missing_information", "routing_status": "not_routed", "validated_fields": {"tckn": "x"}, "target_notification": {"body": "internal"}, "applicant_notifications": [{"kind": "missing_information"}]}
        projected = project_case("USER", source)
        self.assertEqual(projected, {"case_id": "c", "state": "needs_review", "validation_status": "missing_information", "routing_status": "not_routed", "applicant_notifications": [{"kind": "missing_information"}]})

    def test_admin_projection_keeps_operational_detail(self):
        source = {"case_id": "c", "state": "completed", "validated_fields": {"business": "Örnek"}, "target_notification": {"body": "unit"}, "applicant_notifications": []}
        projected = project_case("ADMIN", source)
        self.assertEqual(projected["target_notification"]["body"], "unit")
        self.assertEqual(projected["validated_fields"]["business"], "Örnek")

    def test_unknown_role_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "role"):
            project_case("UNIT", {"case_id": "c", "state": "received", "applicant_notifications": []})


if __name__ == "__main__":
    unittest.main()
