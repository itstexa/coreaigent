"""ATDD acceptance tests for F-04 correspondence safety primitives."""

import unittest

from services.workflow.correspondence import (
    MAX_DRAFT_CHARACTERS,
    MAX_SUMMARY_CHARACTERS,
    MIN_COSINE_SIMILARITY,
    NoSourceLegalClaimError,
    build_retrieval_context,
    extract_json_object,
    sanitize_text,
    semantic_repair_payload,
    validate_generated_draft,
)


class CorrespondenceAcceptanceTests(unittest.TestCase):
    def test_retrieval_threshold_accepts_exact_limit_and_excludes_lower_scores(self):
        chunks = [
            {"chunk_id": "a", "score": 0.73, "content": "A"},
            {"chunk_id": "b", "score": MIN_COSINE_SIMILARITY, "content": "B"},
            {"chunk_id": "c", "score": MIN_COSINE_SIMILARITY - 0.000001, "content": "C"},
        ]
        source_status, selected = build_retrieval_context(chunks)
        self.assertEqual(source_status, "relevant_source_found")
        self.assertEqual([item["chunk_id"] for item in selected], ["a", "b"])

    def test_retrieval_threshold_returns_no_source_at_limit_minus_epsilon(self):
        source_status, selected = build_retrieval_context([
            {"chunk_id": "below", "score": MIN_COSINE_SIMILARITY - 0.000001, "content": "x"}
        ])
        self.assertEqual(source_status, "no_relevant_source")
        self.assertEqual(selected, [])

    def test_sanitizer_replaces_known_and_residual_pii_but_preserves_incident_location(self):
        source = "Ayşe Yılmaz TCKN 10000000146, eposta ayse@example.com. Zafer Caddesi rögar kapağı."
        value = sanitize_text(
            source,
            known_values={"applicant-name": "Ayşe Yılmaz", "tckn": "10000000146"},
            field_handling={"applicant-name": "redact", "tckn": "redact", "incident-location": "task_required"},
        )
        self.assertIn("{{APPLICANT_NAME}}", value)
        self.assertIn("{{APPLICANT_TCKN}}", value)
        self.assertIn("{{REDACTED_EMAIL_1}}", value)
        self.assertIn("Zafer Caddesi rögar kapağı", value)
        self.assertNotIn("Ayşe Yılmaz", value)
        self.assertNotIn("ayse@example.com", value)

    def test_no_source_guard_allows_administrative_text_and_rejects_claims(self):
        allowed = {"document_summary": "Başvuru alınmıştır.", "recommended_correspondence_type": "information_letter", "draft_text": "Başvurunuz ilgili birime iletilmiştir.", "used_source_refs": []}
        self.assertEqual(validate_generated_draft(allowed, [], "no_relevant_source")["draft_text"], allowed["draft_text"])
        for unsafe in ("5393 sayılı Kanun uyarınca işlem yapılacaktır.", "Madde 12 gereğince işlem zorunludur."):
            payload = allowed | {"draft_text": unsafe}
            with self.assertRaises(NoSourceLegalClaimError):
                validate_generated_draft(payload, [], "no_relevant_source")

    def test_generated_result_limits_accept_exact_and_reject_one_more_character(self):
        base = {"recommended_correspondence_type": "other", "correspondence_type_detail": "d" * 200, "used_source_refs": ["REG-001-chunk-001"]}
        exact = base | {"document_summary": "s" * MAX_SUMMARY_CHARACTERS, "draft_text": "d" * MAX_DRAFT_CHARACTERS}
        self.assertEqual(validate_generated_draft(exact, ["REG-001-chunk-001"], "relevant_source_found")["draft_text"], exact["draft_text"])
        with self.assertRaises(ValueError):
            validate_generated_draft(exact | {"draft_text": "d" * (MAX_DRAFT_CHARACTERS + 1)}, ["REG-001-chunk-001"], "relevant_source_found")

    def test_semantic_repair_relabels_existing_json_values_without_inventing_content(self):
        scores = {
            ("application_abstract", "başvuru belgesi kısa özet summary"): 0.60,
            ("letter_category", "resmi yazışma türü correspondence type"): 0.80,
            ("official_correspondence", "resmi yazışma taslak metni draft letter"): 0.80,
            ("citation_ids", "kullanılan kaynak atıf kimlikleri citation references"): 0.80,
            ("Bilgilendirme Yazısı", "bilgilendirme yazısı information letter"): 0.80,
        }
        repaired = semantic_repair_payload(
            {"application_abstract": "Gürültü şikayeti alınmıştır.", "letter_category": "Bilgilendirme Yazısı", "official_correspondence": "Başvurunuz ilgili birime iletilmiştir.", "citation_ids": []},
            retrieved_refs=[], source_status="no_relevant_source",
            similarity=lambda left, right: scores.get((left, right), 0.0),
        )
        self.assertEqual(repaired, {"document_summary": "Gürültü şikayeti alınmıştır.", "recommended_correspondence_type": "information_letter", "draft_text": "Başvurunuz ilgili birime iletilmiştir.", "used_source_refs": []})

    def test_semantic_repair_never_bypasses_no_source_legal_guard(self):
        def score(left, right):
            return 0.8 if (left, right) in {
                ("summary", "başvuru belgesi kısa özet summary"),
                ("type", "resmi yazışma türü correspondence type"),
                ("draft", "resmi yazışma taslak metni draft letter"),
                ("refs", "kullanılan kaynak atıf kimlikleri citation references"),
            } else 0.0
        with self.assertRaises(NoSourceLegalClaimError):
            semantic_repair_payload({"summary": "Başvuru", "type": "information_letter", "draft": "5393 sayılı Kanun uyarınca işlem yapılacaktır.", "refs": []}, retrieved_refs=[], source_status="no_relevant_source", similarity=score)

    def test_json_extraction_accepts_markdown_but_semantic_repair_rejects_limit_minus_epsilon(self):
        payload = extract_json_object("Önerilen çıktı:\n```json\n{\"özet\": \"Başvuru\"}\n```")
        self.assertEqual(payload, {"özet": "Başvuru"})
        with self.assertRaises(ValueError):
            semantic_repair_payload(
                {"summary": "Başvuru", "type": "information_letter", "draft": "İncelenecektir.", "refs": []},
                retrieved_refs=[],
                source_status="no_relevant_source",
                similarity=lambda _left, _right: 0.599999,
            )

    def test_semantic_repair_can_select_existing_sanitized_document_sentences_for_missing_summary(self):
        def score(left, right):
            return 0.8 if (left, right) in {
                ("correspondence_type", "resmi yazışma türü correspondence type"),
                ("draft_text", "resmi yazışma taslak metni draft letter"),
                ("used_source_refs", "kullanılan kaynak atıf kimlikleri citation references"),
            } else 0.0
        repaired = semantic_repair_payload(
            {"correspondence_type": "information_letter", "sanitized_document": "Başvuru alınmıştır. İlgili birim inceleme yapacaktır.", "draft_text": "Başvurunuz ilgili birime iletilmiştir.", "used_source_refs": []},
            retrieved_refs=[], source_status="no_relevant_source", similarity=score,
        )
        self.assertEqual(repaired["document_summary"], "Başvuru alınmıştır. İlgili birim inceleme yapacaktır.")


if __name__ == "__main__":
    unittest.main()
