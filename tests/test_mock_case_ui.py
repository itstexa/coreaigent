import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from mocks.server import (
    BY_ID,
    mock_case_response,
    mock_correspondence_response,
    mock_routing_response,
)


ROOT = Path(__file__).resolve().parents[1]


def schema(name):
    return json.loads((ROOT / "contracts" / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))


class MockCaseUiContractTests(unittest.TestCase):
    def assert_contract(self, name, payload):
        errors = list(Draft202012Validator(schema(name)).iter_errors(payload))
        self.assertFalse(errors, errors[0].message if errors else "")

    def test_happy_path_ui_projections_match_public_contracts(self):
        item = BY_ID["s05-gurultu-sikayeti"]
        case_id = "case-doc-s05-gurultu-sikayeti"
        case = mock_case_response(case_id, item, admin=True)
        correspondence = mock_correspondence_response(case_id, item)
        routing = mock_routing_response(case_id, item)
        self.assert_contract("case-status-result", case)
        self.assert_contract("case-correspondence-result", correspondence)
        self.assert_contract("case-routing-result", routing)
        self.assertEqual(case["state"], "completed")
        self.assertEqual(case["routing_status"], "routed")
        self.assertIn("operational_context", case)
        self.assertEqual(correspondence["generation_status"], "completed")
        self.assertTrue(correspondence["draft_text"])
        self.assertEqual(routing["routing_status"], "routed")
        self.assertEqual({item["audience"] for item in routing["notifications"]}, {"applicant", "target_unit"})

    def test_review_path_does_not_invent_validation_or_route(self):
        item = BY_ID["s10-okunamayan-tarama"]
        case_id = "case-doc-s10-okunamayan-tarama"
        case = mock_case_response(case_id, item)
        route = mock_routing_response(case_id, item)
        self.assertEqual(case["state"], "needs_review")
        self.assertIsNone(case["validation_status"])
        self.assertEqual(route["routing_status"], "not_routed")


if __name__ == "__main__":
    unittest.main()
