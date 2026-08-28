import unittest

from services.workflow.dlp import DlpError, redact_text


class DlpTests(unittest.TestCase):
    def test_redacts_document_specific_name_and_tckn_spans(self):
        source = "Ad Soyad: Ayşe Yılmaz\nTCKN: 12345678903\nTalep: park bakımı"
        result = redact_text(source)
        self.assertEqual(result["text"], "Ad Soyad: <ANON_NAME>\nTCKN: <ANON_TCKN>\nTalep: park bakımı")
        self.assertNotIn("Ayşe Yılmaz", result["text"])
        self.assertNotIn("12345678903", result["text"])
        self.assertEqual({item["field"] for item in result["redactions"]}, {"name", "tckn"})

    def test_redacts_dynamic_name_value_from_validation(self):
        result = redact_text("Başvuru sahibi Ayşe Yılmaz için kayıt.", names=("Ayşe Yılmaz",))
        self.assertEqual(result["text"], "Başvuru sahibi <ANON_NAME> için kayıt.")

    def test_unrelated_text_and_empty_text_are_preserved(self):
        self.assertEqual(redact_text("Park bakımı talebi") ["text"], "Park bakımı talebi")
        self.assertEqual(redact_text("") ["text"], "")

    def test_missing_dynamic_name_fails_closed(self):
        with self.assertRaises(DlpError):
            redact_text("Başvuru metni", names=("Ayşe Yılmaz",))

    def test_non_text_input_fails_closed(self):
        with self.assertRaises(DlpError):
            redact_text(None)


if __name__ == "__main__":
    unittest.main()
