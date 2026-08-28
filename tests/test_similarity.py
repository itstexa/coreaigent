import unittest
from datetime import date

from services.workflow.similarity import similar_case


def case(day, classification="c1", text="park", location="a"):
    return {"created_at": day, "classification": classification, "text": text, "location": location}


class SimilarityTests(unittest.TestCase):
    def test_same_classification_at_exact_30_day_boundary_is_similar(self):
        result = similar_case(case(date(2026, 1, 31)), case(date(2026, 1, 1)))
        self.assertTrue(result["similar"])
        self.assertEqual(result["age_days"], 30)

    def test_one_day_beyond_boundary_is_not_similar(self):
        result = similar_case(case(date(2026, 2, 1)), case(date(2026, 1, 1)))
        self.assertFalse(result["similar"])
        self.assertEqual(result["age_days"], 31)

    def test_different_classification_is_not_similar(self):
        self.assertFalse(similar_case(case(date(2026, 1, 2)), case(date(2026, 1, 1), "c2"))["similar"])

    def test_candidate_from_the_future_is_not_similar(self):
        result = similar_case(case(date(2026, 1, 1)), case(date(2026, 1, 2)))
        self.assertFalse(result["similar"])
        self.assertEqual(result["age_days"], -1)

    def test_zero_day_window_accepts_only_same_day(self):
        self.assertTrue(similar_case(case(date(2026, 1, 1)), case(date(2026, 1, 1)), window_days=0)["similar"])
        self.assertFalse(similar_case(case(date(2026, 1, 2)), case(date(2026, 1, 1)), window_days=0)["similar"])

    def test_text_and_location_matches_are_reported_as_signals(self):
        result = similar_case(case(date(2026, 1, 2), text="park bakım talebi", location="Atatürk Caddesi"), case(date(2026, 1, 1), text="park talebi", location="Atatürk Caddesi"))
        self.assertEqual(set(result["signals"]), {"classification", "time", "text", "location"})


if __name__ == "__main__":
    unittest.main()
