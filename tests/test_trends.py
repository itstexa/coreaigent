import unittest

from services.workflow.trends import flagged_rate


class TrendTests(unittest.TestCase):
    def test_groups_below_five_are_suppressed_and_rate_is_exact(self):
        rows = [{"unit": "u1", "flagged": value} for value in [True, False, True, False, False]]
        rows += [{"unit": "u2", "flagged": True}] * 4
        result = flagged_rate(rows, "unit")
        self.assertEqual(result["u1"], {"total": 5, "flagged": 2, "rate": 0.4})
        self.assertNotIn("u2", result)

    def test_unknown_scope_values_do_not_create_group(self):
        self.assertEqual(flagged_rate([{"flagged": True}], "unit"), {})


if __name__ == "__main__":
    unittest.main()
