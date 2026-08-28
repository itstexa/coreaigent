import unittest

from services.workflow.draft import make_draft, validate_draft


class DraftTests(unittest.TestCase):
    def test_supported_type_is_editable_temporary_and_not_final(self):
        result = make_draft("complaint", {"subject": "Yol", "body": "Bozuk", "full_name": "Ada", "contact": "x"})
        self.assertTrue(result["temporary"])
        self.assertTrue(result["editable"])
        self.assertFalse(result["legal_finality"])
        self.assertEqual(result["missing_fields"], [])

    def test_missing_fields_are_reported_without_rejecting_draft(self):
        result = make_draft("petition/request", {"subject": "Konu"})
        self.assertEqual(result["missing_fields"], ["body", "full_name", "contact"])

    def test_unsupported_type_and_oversized_text_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            validate_draft("official_letter", {}, "metin")
        with self.assertRaisesRegex(ValueError, "invalid_text"):
            validate_draft("complaint", {}, "x" * 20001)


if __name__ == "__main__":
    unittest.main()
