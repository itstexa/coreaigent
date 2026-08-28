import unittest
from datetime import datetime, timezone, timedelta

from services.workflow.priority import apply_override, calculate_priority, queue_order


class PriorityTests(unittest.TestCase):
    NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_default_is_normal_with_visible_reason(self):
        result = calculate_priority({}, now=self.NOW)
        self.assertEqual(result["level"], "normal")
        self.assertIn("default", result["reason"])

    def test_verified_and_policy_signals_raise_deterministically(self):
        policy = {"urgent_request_types": ["fire"], "high_request_types": ["road"]}
        self.assertEqual(calculate_priority({"request_type": "fire"}, policy, now=self.NOW)["level"], "urgent")
        self.assertEqual(calculate_priority({"request_type": "road"}, policy, now=self.NOW)["level"], "high")
        self.assertEqual(calculate_priority({"verified_urgency": True}, now=self.NOW)["level"], "urgent")

    def test_sensitive_data_or_unverified_text_alone_does_not_raise(self):
        result = calculate_priority({"sensitive_data": True, "emergency_text": "acil"}, now=self.NOW)
        self.assertEqual(result["level"], "normal")

    def test_waiting_and_deadline_boundaries(self):
        self.assertEqual(calculate_priority({"waiting_days": 3}, now=self.NOW)["level"], "high")
        self.assertEqual(calculate_priority({"waiting_days": 3 - 1e-6}, now=self.NOW)["level"], "normal")
        self.assertEqual(calculate_priority({"waiting_days": 7}, now=self.NOW)["level"], "urgent")
        deadline = (self.NOW + timedelta(hours=24)).isoformat()
        self.assertEqual(calculate_priority({"deadline": deadline}, now=self.NOW)["level"], "urgent")

    def test_override_requires_nonempty_reason_and_queue_does_not_route(self):
        with self.assertRaisesRegex(ValueError, "reason"):
            apply_override({"level": "normal"}, "urgent", "  ")
        rows = [{"id": "a", "priority": "normal", "unit": "u1"}, {"id": "b", "priority": "urgent", "unit": "u2"}]
        ordered = queue_order(rows)
        self.assertEqual([row["id"] for row in ordered], ["b", "a"])
        self.assertEqual([row["unit"] for row in ordered], ["u2", "u1"])


if __name__ == "__main__":
    unittest.main()
