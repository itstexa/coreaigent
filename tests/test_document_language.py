"""Tests for the document-language boundary: detect once, then answer in kind.

F-01 decides the language of the applicant's own text, stores it, and every later
step that talks to the model or to the applicant reads that one decision.  These
tests pin the two things that would silently break the chain: a detector that
guesses when it should abstain, and a prompt that stays Turkish for an English
document -- which would answer the applicant in a language they did not write in.
"""

import json
import os
import sys
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / "services" / "workflow"
sys.path.insert(0, str(WORKFLOW))
# Both workflow workers read DATABASE_URL at import time and connect lazily, so a
# placeholder is enough to reach the pure prompt builders under test.
os.environ.setdefault("DATABASE_URL", "postgresql://language-tests/unused")

from services.classification.app import classification_reason, classify, load_taxonomy  # noqa: E402
from services.ocr.app import detect_language  # noqa: E402
from services.validation.app import FieldDefinition, extraction_prompt  # noqa: E402

import routing_worker  # noqa: E402
import worker  # noqa: E402


TURKISH_PETITION = (
    "Sayın yetkili, işyerim için ruhsat başvurusu yapmak istiyorum. "
    "Gerekli belge ve izin evraklarını ekte sunuyorum."
)
ENGLISH_PETITION = (
    "I am a resident of the neighbourhood and there has been continuous noise from the "
    "venue on Atatürk Street. I kindly request that your authorities inspect the location "
    "and end this disturbance so the peace and quiet of the area is restored."
)


def scenario_text(text):
    """Pad a fixture the way the scenario runner does.

    Intake rejects anything under 40 normalized characters, so the runner appends
    this sentence; the detector has to be measured against the text that actually
    reaches the service, not the shorter fixture in the file.
    """
    return text if len(text) >= 40 else text + " Test senaryosu için ek açıklama."


class DetectionTests(unittest.TestCase):
    def test_a_turkish_petition_is_turkish(self):
        self.assertEqual(detect_language(TURKISH_PETITION), "tr")

    def test_an_english_petition_with_turkish_place_names_is_still_english(self):
        self.assertEqual(detect_language(ENGLISH_PETITION), "en")

    def test_a_short_turkish_sentence_without_function_words_is_still_turkish(self):
        # Real intake text is often one sentence long; Turkish orthography has to
        # be enough on its own, or every short petition would arrive unlabelled.
        self.assertEqual(detect_language("Gece saatlerinde gürültü nedeniyle şikayetçiyim."), "tr")

    def test_text_carrying_no_language_signal_abstains_instead_of_guessing(self):
        for text in ("", "12345 67890", "Invoice 2024-11 total 500 USD", None):
            self.assertEqual(detect_language(text), "unknown", repr(text))

    def test_every_golden_scenario_document_is_recognised_as_turkish(self):
        # The acceptance runners assert on this, and a scenario that stopped being
        # Turkish would change which prompt its case is processed with.
        scenarios = json.loads((Path(__file__).parents[1] / "scenarios" / "golden-scenarios.json").read_text(encoding="utf-8"))["scenarios"]
        detected = {scenario["id"]: detect_language(scenario_text(scenario["text"])) for scenario in scenarios}
        self.assertEqual({identifier for identifier, code in detected.items() if code != "tr"}, set())


class MultilingualClassificationTests(unittest.TestCase):
    """English keywords must not change any Turkish score.

    The score is matched keywords over list length, so merging both languages
    into one list would halve every Turkish score and demote cases that classify
    today.  Per-language lists keep each denominator to its own language.
    """

    def setUp(self):
        self.taxonomy = load_taxonomy()

    def test_a_turkish_petition_still_classifies_from_the_turkish_keywords(self):
        result = classify(TURKISH_PETITION, self.taxonomy)
        self.assertEqual((result["status"], result["requestType"]["id"]), ("classified", "ruhsat-basvurusu"))
        self.assertEqual(result["confidence"], 1.0)
        self.assertIn("tr keywords", classification_reason(result))

    def test_an_english_petition_classifies_from_the_english_keywords(self):
        result = classify(ENGLISH_PETITION, self.taxonomy)
        self.assertEqual((result["status"], result["requestType"]["id"]), ("classified", "gurultu-sikayeti"))
        self.assertIn("en keywords", classification_reason(result))

    def test_a_plain_keyword_list_is_still_read_as_turkish_only(self):
        mapping = json.loads(Path(self.taxonomy_path()).read_text(encoding="utf-8"))
        for request_type in mapping["requestTypes"]:
            request_type["keywords"] = request_type["keywords"]["tr"]
        legacy = type(self.taxonomy).from_mapping(mapping)
        self.assertEqual(classify(TURKISH_PETITION, legacy)["confidence"], 1.0)
        self.assertEqual(classify(ENGLISH_PETITION, legacy)["confidence"], 0.0)

    def test_a_partial_keyword_match_still_needs_human_review(self):
        # The threshold is strict: 4 of 5 keywords scores 0.8 and does not pass.
        # English is held to exactly the same bar Turkish is, so a petition that
        # only partly matches is reviewed rather than routed on a guess.
        result = classify("I am a resident reporting noise that disturbs the quiet of our street.", self.taxonomy)
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual(result["confidence"], 0.8)

    def test_the_response_never_leaks_the_matched_keyword_language_as_a_field(self):
        from services.classification.app import classify_payload

        payload = classify_payload({"requestId": "r", "documentId": "d", "workflowId": "w", "text": ENGLISH_PETITION}, self.taxonomy)
        self.assertNotIn("keywordLanguage", payload)

    def taxonomy_path(self):
        return Path(__file__).parents[1] / "services" / "classification" / "taxonomy.json"


class PromptLanguageTests(unittest.TestCase):
    DEFINITIONS = (FieldDefinition("business_name", "İşyeri adı", "text", True),)
    ROW = ("case", 1, "gurultu-sikayeti", "Zabıta Müdürlüğü", "Denetim Birimi", "text", {}, "en")

    def test_f03_extraction_asks_in_the_document_language(self):
        self.assertIn("Return only a JSON object", extraction_prompt("text", self.DEFINITIONS, "en"))
        self.assertIn("Yalnız JSON object döndür", extraction_prompt("text", self.DEFINITIONS, "tr"))

    def test_f03_keeps_the_english_field_ids_in_both_languages(self):
        for language in ("tr", "en"):
            self.assertIn("business_name", extraction_prompt("text", self.DEFINITIONS, language))

    def test_f04_drafts_an_english_case_in_english(self):
        prompt = worker._prompt(row=self.ROW, semantic_fields={}, sanitized_document="doc", chunks=[], language="en")
        self.assertIn("Produce an official English correspondence draft", prompt)
        self.assertNotIn("Türkçe", prompt)

    def test_f05_writes_the_applicant_their_own_language_and_the_unit_turkish(self):
        context = ("applicant", "case", "gurultu-sikayeti", None, None, None, {}, "en")
        self.assertIn("Produce a short English municipal notification", routing_worker._notification_prompt("applicant", context, None, "en"))
        self.assertIn("Türkçe kısa belediye bildirimi", routing_worker._notification_prompt("target_unit", context, None, "en"))

    def test_an_unknown_language_falls_back_to_the_authority_language(self):
        for language in ("unknown", None, "de"):
            self.assertIn("Yalnız JSON object döndür", extraction_prompt("t", self.DEFINITIONS, language))
            self.assertIn("Türkçe resmî yazışma", worker._prompt(row=self.ROW, semantic_fields={}, sanitized_document="d", chunks=[], language=language))
            self.assertIn("Türkçe kısa belediye", routing_worker._notification_prompt("applicant", ("applicant", "c", "r", None, None, None, {}, language), None, language))


if __name__ == "__main__":
    unittest.main()
