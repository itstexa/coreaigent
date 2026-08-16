"""Unit tests for the draft-generation service."""
import json
import unittest

from jsonschema import Draft202012Validator

from services.draft.engine import generate_draft

ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]
REQUEST_SCHEMA = json.loads((ROOT / "contracts/schemas/draft-request.schema.json").read_text(encoding="utf-8"))
RESPONSE_SCHEMA = json.loads((ROOT / "contracts/schemas/draft-response.schema.json").read_text(encoding="utf-8"))


class DraftServiceTests(unittest.TestCase):
    def test_valid_payload_generates_letter(self):
        payload = {
            "document": "İşlem için gerekli evrakların eksiksiz sunulması talep edilmektedir.",
            "summary": "Yıllık izin talebi için çalışma planı incelenmesi",
            "regulations": ["İdare Hukuku", "Kamu içi yazışma usulü"],
            "routing": "İnsan Kaynakları Müdürlüğü",
            "missing_info": ["Çalışma süresi", "İzin başlangıç tarihi"],
        }
        result = generate_draft(payload)
        self.assertEqual(result["letter_type"], "eksik_bilgi_talebi")
        self.assertIn("Çalışma süresi", result["draft"])
        self.assertEqual(result["references"], payload["regulations"])
        Draft202012Validator(REQUEST_SCHEMA).validate(payload)
        Draft202012Validator(RESPONSE_SCHEMA).validate(result)

    def test_routing_is_supported(self):
        payload = {
            "document": "Kurum dışı yazışma için üst yazı oluşturulması talep edilmektedir.",
            "summary": "Üst yazı ile kurumlar arası bilgi takibi",
            "regulations": ["Yazışma usulü yönetmeliği"],
            "routing": "Yazı İşleri Müdürlüğü",
            "missing_info": [],
        }
        result = generate_draft(payload)
        self.assertEqual(result["letter_type"], "üst_yazı")
        self.assertIn("Yazı İşleri", result["draft"])
        Draft202012Validator(RESPONSE_SCHEMA).validate(result)

    def test_invalid_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_draft({
                "document": "",
                "summary": "Geçersiz istek",
                "regulations": ["Mevzuat"],
                "routing": "Birim",
                "missing_info": [],
            })

    def test_missing_required_field_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_draft({
                "document": "Doküman metni",
                "summary": "Özet",
                "regulations": ["Mevzuat"],
                "routing": "Birim",
            })


if __name__ == "__main__":
    unittest.main()
