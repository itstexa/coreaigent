"""Falsification tests for F0's safe, immutable case-action projection."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "services" / "workflow"))

from app import action_log_item, ticket_reference  # noqa: E402


class TicketReferenceTests(unittest.TestCase):
    def test_reference_is_stable_and_case_specific(self):
        case = "3f9f9f6e-4d7e-4b3a-9c1e-2a1b0c9d8e7f"
        self.assertEqual(ticket_reference(case), "CA-3F9F9F6E")
        self.assertNotEqual(ticket_reference(case), ticket_reference("4f9f9f6e-4d7e-4b3a-9c1e-2a1b0c9d8e7f"))


class ActionLogProjectionTests(unittest.TestCase):
    when = datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)

    def test_projects_only_the_safe_state_change_facts(self):
        item = action_log_item((7, "state_projected", "system", {
            "revision": 2, "state": "completed", "completed_steps": ["F-01", "F-02"],
            "last_error_code": None, "draft_text": "must never leave PostgreSQL", "tckn": "10000000146",
        }, self.when))
        self.assertEqual(item, {
            "action_id": 7, "type": "state_projected", "actor": "system",
            "state": "completed", "case_revision": 2, "completed_steps": ["F-01", "F-02"],
            "last_error_code": None, "occurred_at": "2026-08-28T08:00:00+00:00",
        })
        self.assertNotIn("draft_text", item)
        self.assertNotIn("tckn", item)

    def test_rejects_an_unrecognised_persisted_action_type(self):
        with self.assertRaisesRegex(ValueError, "action type"):
            action_log_item((8, "operator_note", "system", {}, self.when))

    def test_empty_optional_facts_are_explicit_not_fabricated(self):
        item = action_log_item((9, "state_projected", "system", {}, self.when))
        self.assertIsNone(item["state"])
        self.assertIsNone(item["case_revision"])
        self.assertEqual(item["completed_steps"], [])
        self.assertIsNone(item["last_error_code"])


if __name__ == "__main__":
    unittest.main()
