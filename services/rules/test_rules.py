"""Unit tests for the dependency-free Rule Engine baseline."""
import json
import unittest

from services.rules import analyze_with_rules


SAMPLES = {
    "dilekçe": "Sayın Yetkili, size bir talepte bulunmak istiyorum. Adım Ahmet Yılmaz. Telefon: 0555 000 0000",
    "şikayet": "Şikayet: Mahallemizde sürekli gürültü var, rahatsız oluyoruz. Lütfen inceleyin.",
    "bilgi_talebi": "Merhaba, belediyenin emlak vergisi ödeme tarihlerini öğrenmek istiyorum.",
    "başvuru_formu": "Başvuru: Proje desteği için başvuruyorum. Adım Ayşe Yılmaz, kayıt belgelerim ektedir.",
    "itiraz": "İtiraz: Haksız bir ceza kesildi, itiraz ediyorum ve yeniden inceleme talep ediyorum.",
}


class RuleEngineTests(unittest.TestCase):
    def test_five_document_types_are_analyzed(self):
        for expected_type, text in SAMPLES.items():
            with self.subTest(document_type=expected_type):
                result = analyze_with_rules(text)
                self.assertEqual(result["document_type"], expected_type)
                self.assertIn("recommended_department", result)
                self.assertIn("missing_fields", result)
                self.assertGreaterEqual(result["document_type_score"], 0.0)
                self.assertLessEqual(result["document_type_score"], 1.0)
                self.assertGreaterEqual(result["department_score"], 0.0)
                self.assertLessEqual(result["department_score"], 1.0)
                self.assertIn("olasılık/confidence değil", result["notes"])
                json.dumps(result)

    def test_score_is_not_max_over_max_confidence(self):
        result = analyze_with_rules("Şikayet: Gürültü nedeniyle rahatsızım.")
        self.assertLess(result["document_type_score"], 1.0)
        self.assertLess(result["department_score"], 1.0)

    def test_non_string_is_rejected(self):
        with self.assertRaises(TypeError):
            analyze_with_rules(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
