import unittest

from services.workflow.abuse import analyze_submission


class AbusePolicyTests(unittest.TestCase):
    def test_duplicate_and_burst_are_flagged_with_bounded_score(self):
        result = analyze_submission("aynı metin", ["aynı metin"], recent_count=6)
        self.assertTrue(result["flagged"])
        self.assertEqual(result["detected_signals"], ["duplicate", "burst"])
        self.assertGreaterEqual(result["risk_score"], 0.0)
        self.assertLessEqual(result["risk_score"], 1.0)

    def test_criticism_and_capitals_alone_are_not_abuse(self):
        result = analyze_submission("BU HİZMETİ ELEŞTİRİYORUM", recent_count=1)
        self.assertFalse(result["flagged"])
        self.assertEqual(result["detected_signals"], [])

    def test_configured_term_and_bot_repeat_can_cross_threshold(self):
        result = analyze_submission("tehdit", ["tehdit", "tehdit", "tehdit"], config={"threshold": 0.5})
        self.assertTrue(result["flagged"])
        self.assertIn("threat", result["detected_signals"])
        self.assertIn("bot_repeat", result["detected_signals"])

    def test_non_string_input_fails_closed(self):
        with self.assertRaises(ValueError):
            analyze_submission(None)


if __name__ == "__main__":
    unittest.main()
