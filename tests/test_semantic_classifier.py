"""F-02 anlamsal sınıflandırma modeli (`demo-semantic-v3`).

Anahtar kelime modeli bir istek tipinin bütün kelimelerini aynı metinde görmek
zorunda; vatandaşın kendi cümleleriyle yazdığı bir dilekçe bu testi hiçbir zaman
geçemez.  Buradaki testler serbest metnin doğru birime düştüğünü, kararın
gerekçesinin insana okunabilir kaldığını ve US-107 kabul testlerini donduran
anahtar kelime modelinin değişmediğini birlikte tutuyor.
"""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Her servisin giriş modülü `app` adını taşıyor, bu yüzden düz bir içe aktarma
# suitede ilk yüklenen servise bağlanır.  Sınıflandırıcıyı kendi adıyla yüklemek
# istenen modülün alınmasını garanti eder.
_SPEC = importlib.util.spec_from_file_location(
    "classification_app_semantic", ROOT / "services" / "classification" / "app.py"
)
app = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(app)

NOISE_PETITION = (
    "Oturduğum apartmanın altındaki kafe her gece saat 02.00'ye kadar yüksek sesle "
    "müzik çalıyor. Gürültüden dolayı çocuklarımız uyuyamıyor, komşularımız da "
    "rahatsız. Gereğinin yapılmasını şikayetçi olarak talep ediyorum."
)


class TextFoldingTests(unittest.TestCase):
    def test_loose_folds_turkish_diacritics(self):
        self.assertEqual(app._loose("Gürültü"), "gurultu")
        self.assertEqual(app._loose("İŞYERİ"), "isyeri")

    def test_loose_drops_combining_dot_from_capital_i(self):
        # "İkamet".casefold() bir birleşen noktayla ("i" + U+0307) sonuçlanır ve
        # sadeleştirilmezse hiçbir sinyal eşleşmez.
        self.assertNotIn("̇", app._loose("İkamet"))
        self.assertEqual(app._loose("İkamet"), "ikamet")

    def test_tokens_keep_words_and_drop_numbers(self):
        self.assertEqual(app._tokens("Saat 02.00'de gürültü!"), ("saat", "de", "gurultu"))


class SignalMatchingTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = app.load_taxonomy()
        self.by_id = {item["id"]: item for item in self.taxonomy.request_types}

    def _match(self, group, text):
        return app._match_signal(group, app._tokens(text), app._loose(text))

    def test_prefix_match_follows_turkish_suffixes(self):
        self.assertEqual(self._match(("gurultu",), "Gürültüden bıktık"), "gurultu")
        self.assertEqual(self._match(("sikayet",), "Şikayetçiyim"), "sikayet")

    def test_exact_marker_refuses_unrelated_prefix(self):
        # "geçen" yalın hâlde "gece" ile başlıyor; işaretsiz bir önek eşleşmesi
        # "geçen ay" ifadesini gece gürültüsü sinyali sayardı.
        self.assertIsNone(self._match(("gece$",), "Geçen ay başvurdum"))
        self.assertEqual(self._match(("gece$",), "Her gece tekrarlanıyor"), "gece$")

    def test_multi_word_form_is_matched_in_text(self):
        self.assertEqual(self._match(("yerlesim yeri",), "Yerleşim yeri adresim değişti"), "yerlesim yeri")

    def test_short_form_needs_a_whole_token(self):
        self.assertIsNone(self._match(("ses",), "Sesler geliyor"))
        self.assertEqual(self._match(("ses",), "Ses çok yüksek"), "ses")

    def test_signal_sets_fall_back_to_keywords(self):
        groups = app.signal_sets({"keywords": {"tr": ["ruhsat", "izin"]}})
        self.assertEqual(groups, {"tr": (("ruhsat",), ("izin",))})

    def test_every_request_type_declares_signals_in_both_languages(self):
        for request_type in self.taxonomy.request_types:
            groups = app.signal_sets(request_type)
            self.assertEqual(sorted(groups), ["en", "tr"], request_type["id"])
            for language, listed in groups.items():
                self.assertGreaterEqual(len(listed), app.REQUIRED_SIGNALS, f"{request_type['id']}/{language}")
                for group in listed:
                    self.assertTrue(all(isinstance(form, str) and form for form in group), request_type["id"])

    def test_coverage_denominator_is_the_required_signal_count(self):
        score, matched, language, count, total = app.signal_coverage(NOISE_PETITION, self.by_id["gurultu-sikayeti"])
        self.assertEqual(language, "tr")
        self.assertEqual(score, 1.0)
        self.assertGreaterEqual(count, app.REQUIRED_SIGNALS)
        self.assertEqual(total, len(app.signal_sets(self.by_id["gurultu-sikayeti"])["tr"]))
        self.assertEqual(len(matched), count)

    def test_coverage_is_capped_at_one(self):
        self.assertLessEqual(app.signal_coverage(NOISE_PETITION, self.by_id["gurultu-sikayeti"])[0], 1.0)

    def test_unrelated_text_scores_zero(self):
        self.assertEqual(app.signal_coverage("Merhaba, teşekkür ederim.", self.by_id["gurultu-sikayeti"])[0], 0.0)


class FreeTextClassificationTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = app.load_taxonomy()

    def _classify(self, text):
        return app.classify_semantic(text, self.taxonomy)

    def test_hand_written_noise_complaint_reaches_the_inspection_unit(self):
        result, evidence = self._classify(NOISE_PETITION)
        self.assertEqual(result["status"], "classified")
        self.assertEqual(result["requestType"]["id"], "gurultu-sikayeti")
        self.assertEqual(result["unit"]["id"], "denetim")
        self.assertEqual(result["department"]["id"], "zabita")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["keywordLanguage"], "tr")
        self.assertGreaterEqual(len(evidence["matched"]), evidence["needed"])

    def test_petition_typed_without_diacritics_still_classifies(self):
        result, _ = self._classify(
            "Yan binada gece geç saatlere kadar suren dugun var, gurultu dayanilmaz "
            "halde, uyuyamiyoruz. Sikayetimi iletiyorum."
        )
        self.assertEqual(result["requestType"]["id"], "gurultu-sikayeti")

    def test_english_petition_routes_with_its_own_signal_set(self):
        result, evidence = self._classify(
            "The bar downstairs plays loud music every night until 3am. The noise "
            "disturbs our sleep and my neighbours are complaining."
        )
        self.assertEqual(result["requestType"]["id"], "gurultu-sikayeti")
        self.assertEqual(result["keywordLanguage"], "en")
        self.assertEqual(evidence["language"], "en")

    def test_licence_application_and_status_query_are_told_apart(self):
        application, _ = self._classify(
            "Merkez Mahallesi'nde bir lokanta açmak istiyorum. İşyeri açma ve çalışma "
            "ruhsatı başvurusunda bulunmak için gerekli belgeleri ekte sunuyorum."
        )
        query, _ = self._classify(
            "Geçen ay yaptığım işyeri ruhsatı başvurumun hangi aşamada olduğunu "
            "öğrenmek istiyorum. Sonuç ne zaman açıklanacak?"
        )
        self.assertEqual(application["requestType"]["id"], "ruhsat-basvurusu")
        self.assertEqual(query["requestType"]["id"], "ruhsat-sorgusu")

    def test_richer_evidence_wins_a_capped_tie(self):
        # İki tip de 1.0'a tavanlanabilir; kararı taşıyan sinyal sayısı verir.
        _, evidence = self._classify(
            "Geçen ay yaptığım işyeri ruhsatı başvurumun hangi aşamada olduğunu "
            "öğrenmek istiyorum. Sonuç ne zaman açıklanacak?"
        )
        self.assertEqual(evidence["runnerUp"][0], "Ruhsat Başvurusu")
        self.assertGreater(len(evidence["matched"]), app.REQUIRED_SIGNALS)

    def test_petition_without_any_topic_signal_is_left_to_a_human(self):
        result, evidence = self._classify("Merhaba, bir konuda yardımınıza ihtiyacım var. Teşekkür ederim.")
        self.assertEqual(result["status"], "needs_review")
        self.assertIsNone(result["requestType"])
        self.assertIsNone(result["unit"])
        self.assertIsNone(result["keywordLanguage"])
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(evidence["matched"], ())


class ReasonTextTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = app.load_taxonomy()

    def test_reason_names_the_matched_signals_and_the_alternative(self):
        result, evidence = app.classify_semantic(NOISE_PETITION, self.taxonomy)
        reason = app.semantic_reason(result, evidence)
        self.assertIn("konu sinyalinden", reason)
        self.assertIn("tr sinyal kümesi", reason)
        for form in evidence["matched"]:
            self.assertIn(form, reason)
        if evidence["runnerUp"]:
            self.assertIn("En yakın alternatif", reason)

    def test_reason_for_an_unclassifiable_petition_asks_for_review(self):
        result, evidence = app.classify_semantic("Merhaba, teşekkür ederim.", self.taxonomy)
        self.assertIn("insan incelemesi", app.semantic_reason(result, evidence))


class ClassifyDocumentTests(unittest.TestCase):
    def setUp(self):
        self.taxonomy = app.load_taxonomy()

    def test_default_model_is_the_semantic_one(self):
        result, version, reason = app.classify_document(NOISE_PETITION, self.taxonomy)
        self.assertEqual(version, app.SEMANTIC_CLASSIFIER_VERSION)
        self.assertEqual(result["requestType"]["id"], "gurultu-sikayeti")
        self.assertIn("konu sinyalinden", reason)

    def test_keyword_model_stays_reachable_and_unchanged(self):
        # US-107 kabul testleri anahtar kelime modelini donduruyor: aynı metin
        # aynı sonucu ve aynı gerekçeyi vermeye devam etmeli.
        text = "Adres değişikliği bildirimi için ikamet nakil beyan dilekçesi"
        frozen = app.classify(text, self.taxonomy)
        result, version, reason = app.classify_document(text, self.taxonomy, model="keyword-v2")
        self.assertEqual(version, app.KEYWORD_CLASSIFIER_VERSION)
        self.assertEqual(result, frozen)
        self.assertEqual(reason, app.classification_reason(frozen))

    def test_keyword_model_cannot_read_a_hand_written_petition(self):
        # Modeli değiştirmemizin nedeni: aynı dilekçe eski modelde eşiği aşamıyor.
        frozen = app.classify(NOISE_PETITION, self.taxonomy)
        self.assertEqual(frozen["status"], "needs_review")
        semantic, _ = app.classify_semantic(NOISE_PETITION, self.taxonomy)
        self.assertEqual(semantic["status"], "classified")


if __name__ == "__main__":
    unittest.main()
