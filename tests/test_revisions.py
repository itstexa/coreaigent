import unittest
import uuid

from services.workflow.revisions import edit_decision, next_revision, validate_edit


class RevisionPolicyTests(unittest.TestCase):
    def test_edit_accepts_text_fields_and_attachments_without_classification(self):
        payload = {"text": "Güncellenmiş dilekçe metni", "structured_fields": {"phone": "05551234567"}, "attachment_ids": [str(uuid.uuid4())]}
        self.assertEqual(validate_edit(payload), payload)

    def test_classification_is_never_a_writable_edit_field(self):
        with self.assertRaisesRegex(ValueError, "classification"):
            validate_edit({"classification": "legal"})

    def test_empty_edit_and_bad_shapes_are_rejected(self):
        for payload in ({}, {"text": ""}, {"structured_fields": []}, {"attachment_ids": ["bad"]}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_edit(payload)

    def test_edit_state_policy_and_terminal_boundaries(self):
        for state in ("draft", "waiting_for_information", "review", "routed"):
            self.assertEqual(edit_decision(state, False), "accepted")
        for state in ("completed", "closed"):
            self.assertEqual(edit_decision(state, False), "terminal")
        self.assertEqual(edit_decision("routed", True), "terminal")

    def test_revision_sequence_starts_at_one_and_increments_exactly(self):
        self.assertEqual(next_revision(None), 1)
        self.assertEqual(next_revision(1), 2)
        with self.assertRaises(ValueError):
            next_revision(0)


if __name__ == "__main__":
    unittest.main()
