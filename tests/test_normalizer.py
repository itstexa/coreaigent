import unittest
from services.workflow.normalizer import suggest

class NormalizerTests(unittest.TestCase):
    def test_light_correction_preserves_original_and_protected_spans(self):
        result = suggest("ada 12345678901 , adres 12.05.2026")
        self.assertEqual(result["original_text"], "ada 12345678901 , adres 12.05.2026")
        self.assertIn("12345678901", result["suggested_text"])
        self.assertIn("12.05.2026", result["suggested_text"])
        self.assertIn(",", result["suggested_text"])

    def test_unsupported_language_does_not_translate(self):
        result = suggest("Hello world", "en")
        self.assertEqual(result["status"], "unsupported_language")
        self.assertIsNone(result["suggested_text"])

    def test_empty_text_rejected(self):
        with self.assertRaises(ValueError): suggest(" ")

if __name__ == "__main__": unittest.main()
