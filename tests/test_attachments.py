import unittest

from services.workflow.attachments import (
    MAX_CASE_FILES,
    MAX_FILE_BYTES,
    AttachmentError,
    missing_required_types,
    relation,
    similarity_suggestion,
    validate_metadata,
)


class AttachmentPolicyTests(unittest.TestCase):
    def test_supported_extension_and_matching_mime_are_accepted_at_exact_limit(self):
        result = validate_metadata("foto.JPEG", "image/jpeg", MAX_FILE_BYTES, "objects/case/a")
        self.assertEqual(result["content_type"], "image/jpeg")

    def test_one_byte_over_limit_is_rejected(self):
        with self.assertRaisesRegex(AttachmentError, "10 MiB") as raised:
            validate_metadata("a.pdf", "application/pdf", MAX_FILE_BYTES + 1, "objects/a")
        self.assertEqual(raised.exception.code, "FILE_TOO_LARGE")

    def test_mime_and_extension_must_agree(self):
        with self.assertRaisesRegex(AttachmentError, "MIME"):
            validate_metadata("a.pdf", "image/png", 1, "objects/a")

    def test_unsupported_type_and_path_like_names_are_rejected(self):
        for filename, code in (("a.exe", "FILE_TYPE_NOT_ALLOWED"), ("../a.pdf", "FILENAME_INVALID")):
            with self.subTest(filename=filename):
                with self.assertRaises(AttachmentError) as raised:
                    validate_metadata(filename, "application/pdf", 1, "objects/a")
                self.assertEqual(raised.exception.code, code)

    def test_required_types_are_owned_by_request_type_and_missing_is_explicit(self):
        rules = {"permit_application": ("permit",)}
        self.assertEqual(missing_required_types("permit_application", [], rules), ["permit"])
        self.assertEqual(missing_required_types("permit_application", ["permit"], rules), [])

    def test_relations_distinguish_manual_rule_and_non_authoritative_suggestion(self):
        self.assertTrue(relation("manual", "a", "b")["authoritative"])
        self.assertTrue(relation("rule", "a", "b")["authoritative"])
        self.assertFalse(relation("similarity_suggestion", "a", "b")["authoritative"])

    def test_similarity_is_only_a_suggestion(self):
        result = similarity_suggestion("ruhsat_foto.pdf", [{"attachment_id": "b", "filename": "ruhsat_foto_2.jpg"}])
        self.assertEqual(result[0]["attachment_id"], "b")
        self.assertFalse(result[0]["authoritative"])

    def test_case_limit_is_a_policy_constant(self):
        self.assertEqual(MAX_CASE_FILES, 10)


if __name__ == "__main__":
    unittest.main()
