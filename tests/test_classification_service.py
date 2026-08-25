"""ATDD tests for US-107 F-02 hierarchical classification."""

import unittest

from services.classification.app import Taxonomy, classify, status_for_score


TAXONOMY = {
    "taxonomyVersion": "demo-belediyesi-v1",
    "departments": [
        {"id": "zabita", "label": "Zabıta Müdürlüğü"},
        {"id": "bilgi-islem", "label": "Bilgi İşlem Müdürlüğü"},
    ],
    "units": [
        {"id": "denetim", "label": "Denetim Birimi", "departmentId": "zabita"},
        {"id": "dijital", "label": "Dijital Hizmetler", "departmentId": "bilgi-islem"},
    ],
    "requestTypes": [
        {"id": "gurultu-sikayeti", "label": "Gürültü Şikayeti", "unitId": "denetim", "documentType": "complaint", "keywords": ["gürültü", "gece", "desibel", "rahatsızlık", "şikayet"]},
        {"id": "e-imza-arizasi", "label": "E-İmza Arızası", "unitId": "dijital", "documentType": "complaint", "keywords": ["e-imza", "sertifika", "imzalama", "hata", "sistem"]},
    ],
}


class ClassificationAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = Taxonomy.from_mapping(TAXONOMY)

    def test_threshold_boundary_is_strict(self):
        self.assertEqual(status_for_score(0.799), "needs_review")
        self.assertEqual(status_for_score(0.800), "needs_review")
        self.assertEqual(status_for_score(0.801), "classified")

    def test_complete_match_returns_one_valid_hierarchy(self):
        result = classify("Gece gürültü desibel rahatsızlık şikayet bildiriyorum.", self.taxonomy)

        self.assertEqual(result["status"], "classified")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["department"], {"id": "zabita", "label": "Zabıta Müdürlüğü"})
        self.assertEqual(result["unit"], {"id": "denetim", "label": "Denetim Birimi"})
        self.assertEqual(result["requestType"], {"id": "gurultu-sikayeti", "label": "Gürültü Şikayeti"})
        self.assertNotIn("topCandidates", result)

    def test_exact_threshold_keeps_provisional_chain_without_routing_status(self):
        result = classify("Gece gürültü desibel rahatsızlık bildiriyorum.", self.taxonomy)

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["confidence"], 0.8)
        self.assertEqual(result["department"]["id"], "zabita")
        self.assertEqual(result["requestType"]["id"], "gurultu-sikayeti")

    def test_no_match_is_review_with_null_hierarchy(self):
        result = classify("Bu metin taksonomide yer almayan tamamen özgün bir konudur.", self.taxonomy)

        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["confidence"], 0.0)
        self.assertIsNone(result["department"])
        self.assertIsNone(result["unit"])
        self.assertIsNone(result["requestType"])

    def test_equal_high_scores_choose_stable_request_type_id(self):
        mapping = TAXONOMY | {"requestTypes": TAXONOMY["requestTypes"] + [{
            "id": "a-gurultu-sikayeti", "label": "Alternatif Gürültü Şikayeti",
            "unitId": "denetim", "documentType": "complaint",
            "keywords": ["gürültü", "gece", "desibel", "rahatsızlık", "şikayet"],
        }]}

        result = classify("Gece gürültü desibel rahatsızlık şikayet bildiriyorum.", Taxonomy.from_mapping(mapping))

        self.assertEqual(result["status"], "classified")
        self.assertEqual(result["requestType"]["id"], "a-gurultu-sikayeti")

    def test_invalid_parent_reference_rejects_taxonomy_before_classification(self):
        broken = TAXONOMY | {"units": [{"id": "denetim", "label": "Denetim", "departmentId": "missing"}]}

        with self.assertRaisesRegex(ValueError, "departmentId"):
            Taxonomy.from_mapping(broken)


if __name__ == "__main__":
    unittest.main()
