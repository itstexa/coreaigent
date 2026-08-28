"""Falsification tests for F-06 state and automatic-start decisions."""

import re
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "workflow"))

from orchestrator import MAX_F04_START_ATTEMPTS, derive_case_state, next_start_action, priority_for_text, project_case  # noqa: E402


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


class PriorityTests(unittest.TestCase):
    def test_critical_safety_phrase_wins_over_all_other_signals(self):
        self.assertEqual(priority_for_text("Gaz kaçağı nedeniyle su baskını oluştu.")[:2], ("critical", 100))

    def test_service_impact_phrase_is_high_but_not_critical(self):
        self.assertEqual(priority_for_text("Kanalizasyon taşması ve hijyen sorunu var.")[:2], ("high", 70))

    def test_no_signal_or_empty_text_is_normal(self):
        self.assertEqual(priority_for_text("Parktaki bankın onarılmasını rica ederim.")[:2], ("normal", 40))
        self.assertEqual(priority_for_text(None)[:2], ("normal", 40))


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


class ProjectionWriteTests(unittest.TestCase):
    """The projection runs on every poll, so a no-op pass must not write.

    `updated_at` is what the case list shows as the case's last change.  An
    unconditional upsert rewrites every current case many times a second, which
    both hides the real change time and turns an idle lane into constant write
    traffic.  The statement is assembled from adjacent literals, so the quoting
    between them is removed here to read it as the one string it becomes.
    """

    SOURCE = Path(__file__).parents[1] / "services" / "workflow" / "orchestrator_worker.py"

    def worker_sql(self):
        source = self.SOURCE.read_text(encoding="utf-8")
        return " ".join(re.sub(r'"\s*f?"', "", source).split())

    def test_the_case_state_upsert_only_writes_when_the_projection_changed(self):
        sql = self.worker_sql()
        self.assertIn("INSERT INTO current_case_states", sql)
        self.assertIn("ON CONFLICT (case_id) DO UPDATE", sql)
        guard = sql.split("ON CONFLICT (case_id) DO UPDATE", 1)[1]
        self.assertIn("WHERE", guard)
        for column in ("revision", "completed_steps", "state", "last_error_code", "priority_level", "priority_score", "priority_reason"):
            self.assertIn(f"current_case_states.{column} IS DISTINCT FROM", guard, column)

    def test_a_reviewed_completion_is_never_reopened_by_the_projection(self):
        self.assertIn("current_case_states.state='completed'", self.worker_sql())


if __name__ == "__main__":
    unittest.main()
