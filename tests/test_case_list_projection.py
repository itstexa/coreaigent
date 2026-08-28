"""Falsification tests for the ADMIN case queue projection (GET /cases)."""

import json
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "workflow"))

from app import (  # noqa: E402
    CASE_LIST_SQL, applicant_identity, case_document_item, case_list_bounds,
    case_list_item, related_case_item, text_similarity_score,
)


SCHEMA = Draft202012Validator(json.loads((ROOT / "contracts/schemas/case-list-result.schema.json").read_text(encoding="utf-8")))
UPDATED = datetime(2026, 8, 27, 9, 30, tzinfo=timezone.utc)
CREATED = datetime(2026, 8, 27, 9, 28, tzinfo=timezone.utc)


def row(**overrides):
    """One fully populated joined row, in the query's column order."""
    values = {
        "case_id": "3f9f9f6e-4d7e-4b3a-9c1e-2a1b0c9d8e7f",
        "revision": 2,
        "state": "completed",
        "completed_steps": ["F-01", "F-02", "F-03", "F-04", "F-05"],
        "last_error_code": None,
        "priority_level": "normal",
        "priority_score": 40,
        "priority_reason": "Öncelik sinyali bulunmadı",
        "updated_at": UPDATED,
        "completion_status": "complete",
        "document_id": "doc-1",
        "request_type_id": "gurultu-sikayeti",
        "accepted_fields": {"applicant-name": {"value": "Ayşe Yılmaz", "confidence": 0.8}, "tckn": {"value": "10000000146", "confidence": 1.0}},
        "department_id": "denetim-mudurlugu",
        "department_label": "Denetim Müdürlüğü",
        "unit_id": "denetim",
        "unit_label": "Denetim Birimi",
        "request_type_label": "Gürültü Şikayeti",
        "classification_status": "classified",
        "confidence": Decimal("1.000"),
        "routing_status": "routed",
        "created_at": CREATED,
        "language": "tr",
        "source_metadata": {"title": "Gece gürültüsü şikayeti", "channel": "citizen-portal"},
        "classification_reason": "Gereken 3 konu sinyalinden 5 tanesi bulundu (tr sinyal kümesi): gurultu, gece, rahatsiz, sikayet, komsu.",
    }
    values.update(overrides)
    return tuple(values.values())


class CaseListItemTests(unittest.TestCase):
    def envelope(self, *items):
        return {"total": len(items), "limit": 25, "offset": 0, "cases": list(items)}

    def test_projected_row_matches_the_published_contract(self):
        item = case_list_item(row())
        SCHEMA.validate(self.envelope(item))
        self.assertEqual(item["applicant_name"], "Ayşe Yılmaz")
        self.assertEqual(item["channel"], "citizen-portal")
        self.assertEqual(item["updated_at"], "2026-08-27T09:30:00+00:00")
        self.assertEqual(item["classification_confidence"], 1.0)
        self.assertEqual(item["priority"], {"level": "normal", "score": 40, "reason": "Öncelik sinyali bulunmadı"})
        self.assertIn("konu sinyalinden", item["classification_reason"])

    def test_numeric_confidence_is_json_serialisable(self):
        """psycopg returns numeric(4,3) as Decimal, which json cannot encode."""
        item = case_list_item(row(confidence=Decimal("0.800")))
        self.assertIsInstance(item["classification_confidence"], float)
        json.dumps(item)

    def test_case_that_never_reached_validation_still_lists(self):
        item = case_list_item(row(
            state="needs_review", completed_steps=["F-01", "F-02"], completion_status=None,
            request_type_id=None, accepted_fields=None, routing_status=None,
        ))
        SCHEMA.validate(self.envelope(item))
        self.assertIsNone(item["applicant_name"])
        self.assertIsNone(item["validation_status"])
        self.assertEqual(item["routing_status"], "not_routed")

    def test_missing_projection_columns_never_become_a_fabricated_value(self):
        item = case_list_item(row(
            completed_steps=None, source_metadata=None, created_at=None, language=None,
            department_label=None, unit_label=None, request_type_label=None,
            classification_status=None, confidence=None, classification_reason=None,
        ))
        SCHEMA.validate(self.envelope(item))
        self.assertEqual(item["completed_steps"], [])
        self.assertIsNone(item["title"])
        self.assertIsNone(item["channel"])
        self.assertIsNone(item["created_at"])
        self.assertIsNone(item["classification_confidence"])
        # An operator reading "why" must see nothing rather than a sentence the
        # classifier never wrote.
        self.assertIsNone(item["classification_reason"])

    def test_business_and_supplier_schemas_name_the_applicant_too(self):
        """Three request-type schemas name the applicant with a different field."""
        self.assertEqual(case_list_item(row(accepted_fields={"business-name": {"value": "Örnek Lokanta"}}))["applicant_name"], "Örnek Lokanta")
        self.assertEqual(case_list_item(row(accepted_fields={"supplier-name": {"value": "Örnek Tedarik A.Ş."}}))["applicant_name"], "Örnek Tedarik A.Ş.")

    def test_blank_or_malformed_field_entries_do_not_name_an_applicant(self):
        for accepted in ({}, {"applicant-name": {}}, {"applicant-name": {"value": ""}}, {"applicant-name": None}, {"applicant-name": 5}):
            self.assertIsNone(case_list_item(row(accepted_fields=accepted))["applicant_name"], accepted)

    def test_non_string_metadata_is_not_rendered_as_a_title(self):
        self.assertIsNone(case_list_item(row(source_metadata={"title": 12, "channel": []}))["title"])

    def test_priority_is_projected_as_stored_not_recomputed_in_the_api(self):
        item = case_list_item(row(priority_level="critical", priority_score=100, priority_reason="Gaz kaçağı riski"))
        self.assertEqual(item["priority"], {"level": "critical", "score": 100, "reason": "Gaz kaçağı riski"})


class CaseListBoundsTests(unittest.TestCase):
    def test_default_window(self):
        self.assertEqual(case_list_bounds(25, 0), (25, 0))

    def test_oversized_page_is_clamped_rather_than_rejected(self):
        self.assertEqual(case_list_bounds(5000, 0), (100, 0))

    def test_out_of_range_paging_collapses_to_the_nearest_legal_window(self):
        self.assertEqual(case_list_bounds(0, -5), (1, 0))
        self.assertEqual(case_list_bounds(-1, -1), (1, 0))

    def test_unparseable_paging_falls_back_to_the_default_window(self):
        self.assertEqual(case_list_bounds("x", "y"), (25, 0))
        self.assertEqual(case_list_bounds(None, None), (25, 0))


class RelatedCaseTests(unittest.TestCase):
    def test_same_applicant_key_ignores_turkish_case_and_whitespace(self):
        self.assertEqual(applicant_identity({"applicant-name": {"value": "  Ayşe  IŞIK "}}), "ayse isik")
        self.assertIsNone(applicant_identity({}))

    def test_similarity_threshold_has_an_exact_inclusive_boundary(self):
        self.assertEqual(text_similarity_score("bir iki ucx dort bes", "bir"), 20)
        self.assertEqual(text_similarity_score("bir iki ucx dort bes", "bir alti"), 17)
        self.assertEqual(text_similarity_score("", "bir iki"), 0)

    def test_related_item_exposes_status_but_not_the_petition_or_identity(self):
        item = related_case_item(("case-2", "DOC-2", "completed", CREATED, {"title": "Eski bildirim"}), 60)
        self.assertEqual(item["resolved"], True)
        self.assertEqual(item["similarity_score"], 60)
        self.assertNotIn("text", item)
        self.assertNotIn("applicant_name", item)


class CaseListQueryTests(unittest.TestCase):
    """The queue must not drop a case, and must not lock rows it only reads."""

    def test_projection_starts_from_the_case_state_table_and_outer_joins_the_rest(self):
        sql = " ".join(CASE_LIST_SQL.split()).upper()
        self.assertIn("FROM CURRENT_CASE_STATES CS", sql)
        for joined in ("CURRENT_VALIDATION_STATES", "CURRENT_CLASSIFICATIONS", "ROUTING_OPERATIONS", "INTAKE_RECORDS"):
            self.assertIn(f"LEFT JOIN {joined}", sql)
        # An inner join to validation would hide every needs_review case, which
        # is precisely the queue an operator opens the panel to work through.
        self.assertNotIn("INNER JOIN", sql)

    def test_read_only_projection_takes_no_row_locks(self):
        self.assertNotIn("FOR UPDATE", CASE_LIST_SQL.upper())

    def test_queue_read_sorts_priority_before_newness(self):
        source = (ROOT / "services/workflow/app.py").read_text(encoding="utf-8")
        self.assertIn("ORDER BY cs.priority_score DESC,cs.updated_at DESC,cs.case_id", source)

    def test_routing_is_joined_on_the_projected_revision_only(self):
        sql = " ".join(CASE_LIST_SQL.split())
        self.assertIn("routing_operations r ON r.case_id=cs.case_id AND r.source_case_revision=cs.revision", sql)

    def test_column_count_matches_the_projection_arity(self):
        selected = CASE_LIST_SQL[CASE_LIST_SQL.index("SELECT ") + 7:CASE_LIST_SQL.index(" FROM ")]
        depth, columns = 0, 1
        for character in selected:
            depth += (character == "(") - (character == ")")
            columns += character == "," and depth == 0
        self.assertEqual(columns, len(row()))


class CaseDocumentProjectionTests(unittest.TestCase):
    """GET /cases/{case_id}/document -- the petition an operator reads."""

    schema = Draft202012Validator(json.loads((ROOT / "contracts/schemas/case-document.schema.json").read_text(encoding="utf-8")))
    record = (
        "doc-1", "text", "Alt katımızdaki kafe her gece müzik çalıyor, şikayetçiyim.", "tr",
        {"title": "Gece gürültüsü şikayeti", "channel": "citizen-portal"}, CREATED,
    )

    def test_projected_document_matches_the_published_contract(self):
        item = case_document_item("3f9f9f6e-4d7e-4b3a-9c1e-2a1b0c9d8e7f", self.record)
        self.schema.validate(item)
        self.assertEqual(item["channel"], "citizen-portal")
        self.assertEqual(item["language"], "tr")
        self.assertEqual(item["created_at"], "2026-08-27T09:28:00+00:00")
        self.assertIn("şikayetçiyim", item["text"])

    def test_document_without_metadata_still_carries_the_text(self):
        record = ("doc-2", "ocr", "Scanned petition body", None, None, CREATED)
        item = case_document_item("3f9f9f6e-4d7e-4b3a-9c1e-2a1b0c9d8e7f", record)
        self.schema.validate(item)
        self.assertIsNone(item["title"])
        self.assertIsNone(item["channel"])
        self.assertEqual(item["source_type"], "ocr")

    def test_empty_text_is_projected_as_a_string_not_null(self):
        # The contract promises a string: the panel renders it directly, and a
        # null would print "null" into the operator's reading pane.
        item = case_document_item("3f9f9f6e-4d7e-4b3a-9c1e-2a1b0c9d8e7f", ("doc-3", "text", None, "tr", {}, CREATED))
        self.schema.validate(item)
        self.assertEqual(item["text"], "")


if __name__ == "__main__":
    unittest.main()
