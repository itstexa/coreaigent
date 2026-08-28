"""Falsification tests for F2's deterministic workload assignment policy."""

import sys
import unittest
from datetime import datetime
from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / "services" / "workflow"
sys.path.insert(0, str(WORKFLOW))

from assignment import behavior_signals, choose_staff  # noqa: E402


class AssignmentSelectionTests(unittest.TestCase):
    def test_empty_pool_is_explicitly_unassigned(self):
        self.assertIsNone(choose_staff([]))

    def test_lowest_open_count_wins(self):
        selected = choose_staff([
            {"staff_id": "busy", "open_count": 2},
            {"staff_id": "free", "open_count": 1},
        ])
        self.assertEqual(selected["staff_id"], "free")

    def test_oldest_last_assignment_wins_a_load_tie(self):
        selected = choose_staff([
            {"staff_id": "recent", "open_count": 0, "last_assigned_at": datetime(2026, 8, 28, 9, 10)},
            {"staff_id": "old", "open_count": 0, "last_assigned_at": datetime(2026, 8, 28, 9, 1)},
        ])
        self.assertEqual(selected["staff_id"], "old")

    def test_never_assigned_member_precedes_a_previously_assigned_member(self):
        selected = choose_staff([
            {"staff_id": "known", "open_count": 0, "last_assigned_at": datetime(2026, 8, 28, 9, 1)},
            {"staff_id": "new", "open_count": 0, "last_assigned_at": None},
        ])
        self.assertEqual(selected["staff_id"], "new")

    def test_stable_id_breaks_an_exact_tie(self):
        selected = choose_staff([
            {"staff_id": "staff-b", "open_count": 0, "last_assigned_at": None},
            {"staff_id": "staff-a", "open_count": 0, "last_assigned_at": None},
        ])
        self.assertEqual(selected["staff_id"], "staff-a")

    def test_resolution_rate_wins_for_a_repeated_or_aggressive_case(self):
        selected = choose_staff([
            {"staff_id": "busy-expert", "open_count": 4, "topic_total": 10, "topic_resolved": 9, "resolution_rate": .9},
            {"staff_id": "free-novice", "open_count": 0, "topic_total": 10, "topic_resolved": 5, "resolution_rate": .5},
        ], prioritize_resolution=True)
        self.assertEqual(selected["staff_id"], "busy-expert")

    def test_normal_case_keeps_least_loaded_policy(self):
        selected = choose_staff([
            {"staff_id": "expert", "open_count": 3, "topic_total": 10, "resolution_rate": .9},
            {"staff_id": "free", "open_count": 0, "topic_total": 1, "resolution_rate": .2},
        ])
        self.assertEqual(selected["staff_id"], "free")

    def test_repeat_trigger_is_inclusive_at_three(self):
        self.assertFalse(behavior_signals("", previous_topic_count=1, same_topic=True)["priority_mode"])
        self.assertTrue(behavior_signals("", previous_topic_count=2, same_topic=True)["priority_mode"])

    def test_aggression_signal_has_bounded_score_and_level(self):
        signal = behavior_signals("Bu tehdit ve şiddet kabul edilemez")
        self.assertEqual(signal["aggression_level"], "high")
        self.assertEqual(signal["aggression_score"], 1.0)

    def test_english_aggression_signal_is_scored_without_translation_model(self):
        signal = behavior_signals("This threat and violence are unacceptable", source_language="en")
        self.assertEqual(signal["aggression_level"], "high")
        self.assertEqual(signal["aggression_score"], 1.0)
        self.assertEqual(signal["marker_count"], 3)

    def test_english_neutral_text_does_not_trigger_aggression(self):
        signal = behavior_signals("Please repair the broken street light", source_language="en")
        self.assertEqual(signal["aggression_level"], "normal")
        self.assertEqual(signal["aggression_score"], 0.0)

    def test_marker_inside_an_english_word_is_not_a_signal(self):
        signal = behavior_signals("The skill of the team is improving", source_language="en")
        self.assertEqual(signal["aggression_level"], "normal")
        self.assertEqual(signal["aggression_score"], 0.0)

    def test_common_turkish_frustration_is_visible_to_the_assignment_signal(self):
        signal = behavior_signals("Ne demek böyle ulan, ben sıkıldım artık", source_language="tr")
        self.assertEqual(signal["aggression_level"], "high")
        self.assertEqual(signal["aggression_score"], 0.7)

    def test_empty_text_has_no_behavior_signal(self):
        signal = behavior_signals(None)
        self.assertEqual(signal["aggression_level"], "normal")
        self.assertEqual(signal["aggression_score"], 0.0)


if __name__ == "__main__":
    unittest.main()
