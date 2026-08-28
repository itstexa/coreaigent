import unittest

from services.workflow.action_log import ACTION_TYPES, append_action_log, build_action_event


class Cursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))


class ActionLogTests(unittest.TestCase):
  def test_allowed_case_action_event_contains_case_action_actor(self):
    self.assertEqual(build_action_event("case-1", "view", "USER"), {
        "case_id": "case-1",
        "action_type": "view",
        "actor": "USER",
    })


  def test_unknown_action_is_rejected(self):
    with self.assertRaisesRegex(ValueError, "unknown action_type"):
        build_action_event("case-1", "erase", "ADMIN")


  def test_empty_case_or_actor_is_rejected(self):
    with self.assertRaises(ValueError):
        build_action_event("", "view", "USER")
    with self.assertRaises(ValueError):
        build_action_event("case-1", "view", "")


  def test_boundary_action_types_are_all_accepted(self):
    for action_type in ACTION_TYPES:
        self.assertEqual(build_action_event("case-1", action_type, "ADMIN")["action_type"], action_type)


  def test_append_uses_immutable_insert_and_json_details(self):
    cursor = Cursor()
    event_id = append_action_log(cursor, "case-1", "view", "USER", {"path": "/cases/case-1"})
    self.assertIsNotNone(event_id)
    self.assertIn("INSERT INTO case_action_logs", cursor.calls[0][0])
    self.assertIn("ON CONFLICT (event_id) DO NOTHING", cursor.calls[0][0])
    self.assertEqual(cursor.calls[0][1][1:4], ("case-1", "view", "USER"))
    details = cursor.calls[0][1][4]
    self.assertEqual(getattr(details, "obj", details), {"path": "/cases/case-1"})


  def test_append_rejects_non_object_details(self):
    with self.assertRaisesRegex(ValueError, "details must be an object"):
        append_action_log(Cursor(), "case-1", "view", "USER", ["not-an-object"])


if __name__ == "__main__":
    unittest.main()
