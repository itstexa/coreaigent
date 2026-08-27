"""ATDD unit tests for US-108 F-03 extraction and validation rules."""

import io
import json
import unittest
from unittest.mock import patch

from services.validation import app as validation_app
from services.validation.app import FieldDefinition, evaluate_fields, extract_candidates, validate_value


def field(field_id, kind, required=True):
    return FieldDefinition(field_id, field_id, kind, required)


class ValidationRuleAcceptanceTests(unittest.TestCase):
    def test_tckn_checksum_distinguishes_usable_and_invalid_value(self):
        self.assertEqual(validate_value("tckn", "10000000146", {}), ("10000000146", None))
        self.assertEqual(validate_value("tckn", "12345678901", {}), (None, "tckn_checksum"))
        self.assertEqual(validate_value("tckn", "1000000014", {}), (None, "tckn_checksum"))

    def test_phone_normalization_and_invalid_format(self):
        for source in ("5321234567", "05321234567", "+905321234567"):
            self.assertEqual(validate_value("phone-tr", source, {}), ("+905321234567", None))
        self.assertEqual(validate_value("phone-tr", "02121234567", {}), (None, "phone_format"))

    def test_date_normalization_and_impossible_date(self):
        self.assertEqual(validate_value("date", "25.08.2026", {}), ("2026-08-25", None))
        self.assertEqual(validate_value("date", "2026-08-25", {}), ("2026-08-25", None))
        self.assertEqual(validate_value("date", "2026-02-30", {}), (None, "date_format"))

    def test_free_text_exact_limit_and_neighbors(self):
        self.assertEqual(validate_value("free-text", "a" * 4095, {}), ("a" * 4095, None))
        self.assertEqual(validate_value("free-text", "a" * 4096, {}), ("a" * 4096, None))
        self.assertEqual(validate_value("free-text", "a" * 4097, {}), (None, "schema_rule"))

    def test_missing_and_invalid_are_distinct_with_invalid_priority(self):
        fields = [field("tckn", "tckn"), field("phone", "phone-tr"), field("note", "free-text", False)]
        result = evaluate_fields(fields, {"tckn": "12345678901"}, {}, {})

        self.assertEqual(result["completionStatus"], "invalid_information")
        self.assertEqual(result["missingRequiredFields"], [{"id": "phone", "label": "phone"}])
        self.assertEqual(result["invalidFields"], [{"id": "tckn", "label": "tckn", "code": "tckn_checksum"}])
        self.assertTrue(result["userActionRequired"])

    def test_optional_absence_does_not_block_complete(self):
        result = evaluate_fields([field("name", "free-text"), field("phone", "phone-tr", False)], {"name": "Ayşe Yılmaz"}, {}, {})

        self.assertEqual(result["completionStatus"], "complete")
        self.assertFalse(result["userActionRequired"])
        self.assertEqual(result["missingRequiredFields"], [])
        self.assertEqual(result["invalidFields"], [])

    def test_attachment_requires_persisted_reference_and_does_not_expose_it(self):
        definition = field("invoice-attachment", "attachment")
        missing = evaluate_fields([definition], {}, {}, {})
        present = evaluate_fields([definition], {}, {}, {"attachments": [{"attachmentId": "att-42"}]})
        malformed = evaluate_fields([definition], {}, {}, {"attachments": [{}]})

        self.assertEqual(missing["completionStatus"], "missing_information")
        self.assertEqual(present["completionStatus"], "complete")
        self.assertEqual(present["extractedFields"], [{"id": "invoice-attachment", "label": "invoice-attachment", "value": "present", "confidence": 1.0}])
        self.assertEqual(malformed["completionStatus"], "invalid_information")
        self.assertEqual(malformed["invalidFields"][0]["code"], "attachment_missing")

    def test_jamba_extraction_reads_json_out_of_a_fenced_model_answer(self):
        class Response(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        definitions = [field("tckn", "tckn"), field("applicant-name", "free-text")]
        fenced = json.dumps({"response": 'İsteğiniz:\n```json\n{"applicant-name": "Ayşe Yılmaz"}\n```'})
        with patch.object(validation_app, "EXTRACTOR_MODE", "jamba"), \
                patch("services.validation.app.urllib.request.urlopen", return_value=Response(fenced)):
            candidates = extract_candidates("TCKN 10000000146.", definitions)

        # The rule-owned field still comes from the deterministic pass.
        self.assertEqual(candidates["tckn"], {"value": "10000000146", "confidence": 1.0})
        self.assertEqual(candidates["applicant-name"], {"value": "Ayşe Yılmaz", "confidence": 0.5})

    def test_jamba_extraction_rejects_an_answer_without_any_json_object(self):
        class Response(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        definitions = [field("applicant-name", "free-text")]
        prose = json.dumps({"response": "Bu metinde başvuran adı bulunmuyor."})
        with patch.object(validation_app, "EXTRACTOR_MODE", "jamba"), \
                patch("services.validation.app.urllib.request.urlopen", return_value=Response(prose)):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                extract_candidates("boş", definitions)

    def test_jamba_cannot_override_rule_owned_field_ids(self):
        class Response(io.StringIO):
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        definitions = [field("tckn", "tckn"), field("applicant-name", "free-text")]
        response = Response('{"response":"{\\"tckn\\":\\"12345678901\\",\\"applicant-name\\":\\"Ayşe Yılmaz\\"}"}')
        with patch.object(validation_app, "EXTRACTOR_MODE", "jamba"), patch("services.validation.app.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                extract_candidates("10000000146", definitions)


if __name__ == "__main__":
    unittest.main()
