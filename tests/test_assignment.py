import unittest

from services.workflow.assignment import select_assignee


class AssignmentTests(unittest.TestCase):
    def test_only_routed_unit_members_are_candidates(self):
        people = [
            {"person_id": "a", "unit_id": "u1"},
            {"person_id": "b", "unit_id": "u2"},
        ]
        self.assertEqual(select_assignee(people, {"a": 0, "b": 0}, "u1", chooser=lambda values: values[0])["person_id"], "a")

    def test_lowest_open_case_count_wins(self):
        people = [{"person_id": "a", "unit_id": "u1"}, {"person_id": "b", "unit_id": "u1"}]
        result = select_assignee(people, {"a": 2, "b": 1}, "u1", chooser=lambda values: values[0])
        self.assertEqual(result["person_id"], "b")

    def test_equal_minimums_are_delegated_to_random_chooser(self):
        people = [{"person_id": "a", "unit_id": "u1"}, {"person_id": "b", "unit_id": "u1"}]
        result = select_assignee(people, {"a": 1, "b": 1}, "u1", chooser=lambda values: values[-1])
        self.assertEqual(result["person_id"], "b")

    def test_no_unit_member_returns_no_assignment(self):
        self.assertIsNone(select_assignee([{"person_id": "a", "unit_id": "u2"}], {"a": 0}, "u1", chooser=lambda values: values[0]))

    def test_missing_count_is_zero_and_invalid_person_is_rejected(self):
        people = [{"person_id": "a", "unit_id": "u1"}, {"person_id": "", "unit_id": "u1"}]
        result = select_assignee(people, {}, "u1", chooser=lambda values: values[0])
        self.assertEqual(result["person_id"], "a")


if __name__ == "__main__":
    unittest.main()
