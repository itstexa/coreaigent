"""Falsification tests for the citizen e-petition portal's sample petitions.

The portal no longer composes a petition from a form: the citizen writes free
prose and F-01, F-02 and F-03 have to make sense of it.  That moves the risk.
The old risk was a template drifting from the taxonomy; the new risk is a sample
petition that reads naturally but does not actually classify -- which would put a
misrouted case in front of a demo audience and call it the product.

So these tests run the real services on the real sample text: F-01's language
detector and intake minimum, F-02's configured scoring model, and F-03's own
rule extractor.  Nothing here re-implements a service rule; the file catalogue
checks stay because the portal can only ask a citizen for a field the validation
registry will actually store.
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Every service names its entry module `app`, so a bare `sys.path` import binds
# to whichever service the suite loaded first -- alphabetically the workflow's.
# Loading each service under its own name means the module this test asks for is
# the module it gets, whatever ran before it.
def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


classification_app = _load("classification_app", "services/classification/app.py")
ocr_app = _load("ocr_app", "services/ocr/app.py")
from services.validation import app as validation_app  # noqa: E402  (dataclass needs a real module entry)

CONTENT = json.loads((ROOT / "frontend/src/petition-content.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((ROOT / "services/validation/registry.json").read_text(encoding="utf-8"))
TAXONOMY = classification_app.load_taxonomy()
SAMPLES = CONTENT["samples"]
CATALOG = {field["id"]: field for field in CONTENT["fieldCatalog"]}

# F-01 rejects an intake below this many normalised characters (services/ocr/app.py).
INTAKE_MINIMUM = 40
RENDERABLE_KINDS = {"text", "textarea", "date", "tckn", "phone", "attachment"}
# The kinds the portal can put in front of a citizen; an attachment cannot be
# uploaded there, so it is shown as a note instead of a question.
ASKABLE_KINDS = RENDERABLE_KINDS - {"attachment"}


def uncapped_ratio(text, request_type):
    """The value F-02 actually ranks on, not the capped confidence it reports."""
    _, _, _, matched, groups = classification_app.signal_coverage(text, request_type)
    needed = min(classification_app.REQUIRED_SIGNALS, groups) or 1
    return matched / needed


class SampleIntakeTests(unittest.TestCase):
    """F-01 has to accept the sample and call it Turkish."""

    def test_every_sample_clears_the_intake_minimum(self):
        for sample in SAMPLES:
            with self.subTest(sample["requestTypeId"]):
                self.assertGreaterEqual(len(ocr_app.normalize(sample["sampleText"])), INTAKE_MINIMUM)

    def test_the_portals_own_minimum_is_not_below_the_services(self):
        self.assertGreaterEqual(CONTENT["minTextLength"], INTAKE_MINIMUM)

    def test_every_sample_is_long_enough_for_the_portals_own_check(self):
        for sample in SAMPLES:
            with self.subTest(sample["requestTypeId"]):
                normalised = re.sub(r"\s+", " ", sample["sampleText"]).strip()
                self.assertGreaterEqual(len(normalised), CONTENT["minTextLength"])

    def test_every_sample_is_detected_as_turkish(self):
        for sample in SAMPLES:
            with self.subTest(sample["requestTypeId"]):
                self.assertEqual(ocr_app.detect_language(sample["sampleText"]), "tr")

    def test_no_sample_carries_a_machine_readable_field_line(self):
        """The point of the rewrite: this is a petition, not a form in disguise.

        A `field-id: value` line would be picked up by `labeled_candidates` and
        the demo would be extracting the portal's own output instead of the
        citizen's prose.
        """
        labelled = re.compile(r"(?im)^(%s)\s*:" % "|".join(re.escape(field_id) for field_id in CATALOG))
        for sample in SAMPLES:
            with self.subTest(sample["requestTypeId"]):
                self.assertIsNone(labelled.search(sample["sampleText"]))


class SampleClassificationTests(unittest.TestCase):
    """F-02 has to reach the sample's own request type, with the shipped model."""

    def test_every_sample_names_a_request_type_the_taxonomy_still_publishes(self):
        published = {item["id"] for item in TAXONOMY.request_types}
        for sample in SAMPLES:
            self.assertIn(sample["requestTypeId"], published, sample["label"])

    def test_every_sample_classifies_to_its_own_request_type(self):
        for sample in SAMPLES:
            with self.subTest(sample["requestTypeId"]):
                result, version, reason = classification_app.classify_document(sample["sampleText"], TAXONOMY)
                self.assertEqual(result["requestType"]["id"], sample["requestTypeId"])
                self.assertEqual(result["status"], "classified")
                self.assertEqual(result["confidence"], 1.0)
                self.assertEqual(version, classification_app.SEMANTIC_CLASSIFIER_VERSION)
                self.assertTrue(reason.strip())

    def test_the_unit_hint_shown_to_the_citizen_is_the_unit_that_will_receive_it(self):
        for sample in SAMPLES:
            with self.subTest(sample["requestTypeId"]):
                result, _, _ = classification_app.classify_document(sample["sampleText"], TAXONOMY)
                self.assertEqual(sample["unitHint"], result["unit"]["label"])

    def test_no_competing_request_type_ranks_as_high(self):
        """A tie would hand the case to the alphabet rather than to the citizen."""
        for sample in SAMPLES:
            with self.subTest(sample["requestTypeId"]):
                own = next(item for item in TAXONOMY.request_types if item["id"] == sample["requestTypeId"])
                mine = uncapped_ratio(sample["sampleText"], own)
                for request_type in TAXONOMY.request_types:
                    if request_type["id"] == sample["requestTypeId"]:
                        continue
                    self.assertLess(uncapped_ratio(sample["sampleText"], request_type), mine, request_type["id"])

    def test_the_reason_names_the_evidence_the_citizen_can_check(self):
        """The reason string is the only place the matched signals survive."""
        for sample in SAMPLES:
            with self.subTest(sample["requestTypeId"]):
                result, evidence = classification_app.classify_semantic(sample["sampleText"], TAXONOMY)
                reason = classification_app.semantic_reason(result, evidence)
                self.assertIn("sinyal", reason)
                self.assertTrue(evidence["matched"])
                for form in evidence["matched"]:
                    self.assertIn(form, reason)


class SampleExtractionTests(unittest.TestCase):
    """F-03's deterministic rules have to find what prose can carry deterministically."""

    def schema(self, request_type_id):
        return {field["id"]: field for field in REGISTRY["schemas"][request_type_id]}

    def test_registry_still_publishes_a_schema_for_every_sample(self):
        for sample in SAMPLES:
            self.assertIn(sample["requestTypeId"], REGISTRY["schemas"], sample["label"])

    def test_every_sample_carries_an_identity_number_the_rule_extractor_finds(self):
        for sample in SAMPLES:
            with self.subTest(sample["requestTypeId"]):
                found = validation_app.rule_candidates(sample["sampleText"])
                self.assertIn("tckn", found, "kimlik numarası prose içinde bulunamadı")
                self.assertTrue(validation_app.valid_tckn(found["tckn"]["value"]))

    def test_every_required_date_field_is_findable_without_a_language_model(self):
        """A required date is the one field prose reliably spells out.

        The extractor reads the first date in the text, so a sample whose schema
        requires one must write it before any other date.
        """
        for sample in SAMPLES:
            found = validation_app.rule_candidates(sample["sampleText"])
            for field_id, field in self.schema(sample["requestTypeId"]).items():
                if field["required"] and field["kind"] == "date":
                    with self.subTest(f"{sample['requestTypeId']}/{field_id}"):
                        self.assertIn(field_id, found)

    def test_identity_numbers_are_distinct_across_samples(self):
        """Two samples sharing a number would look like one citizen in the queue."""
        numbers = [validation_app.rule_candidates(sample["sampleText"])["tckn"]["value"] for sample in SAMPLES]
        self.assertEqual(len(set(numbers)), len(numbers))

    def test_no_sample_requires_an_attachment_the_portal_cannot_upload(self):
        for sample in SAMPLES:
            for field_id, field in self.schema(sample["requestTypeId"]).items():
                if field["kind"] == "attachment":
                    self.assertFalse(field["required"], f"{sample['label']}/{field_id}")


class FieldCatalogTests(unittest.TestCase):
    """The catalogue exists only to ask back for what validation reported missing."""

    def test_the_catalogue_covers_every_field_the_registry_can_report(self):
        published = {field["id"] for schema in REGISTRY["schemas"].values() for field in schema}
        self.assertEqual(published - set(CATALOG), set(), "portal cannot ask for these fields")

    def test_the_catalogue_invents_no_field_the_registry_would_discard(self):
        published = {field["id"] for schema in REGISTRY["schemas"].values() for field in schema}
        self.assertEqual(set(CATALOG) - published, set())

    def test_every_catalogue_kind_is_one_the_form_can_render(self):
        for field_id, field in CATALOG.items():
            self.assertIn(field["kind"], RENDERABLE_KINDS, field_id)

    def test_every_required_field_is_either_askable_or_declared_an_attachment(self):
        """Free text can reach a request type the portal cannot fully answer.

        `fatura-islemi` requires an invoice image, and a citizen writing about an
        invoice can classify into it -- the portal has no upload, so that field
        must be recognisable as an attachment and shown as a note ("kuruma elden
        iletin") instead of being asked as a question with no answer.
        """
        for schema in REGISTRY["schemas"].values():
            for field in schema:
                if field["required"]:
                    with self.subTest(field["id"]):
                        kind = CATALOG[field["id"]]["kind"]
                        self.assertIn(kind, ASKABLE_KINDS | {"attachment"})
                        if field["kind"] == "attachment":
                            self.assertEqual(kind, "attachment", "portal would ask for a file as text")

    def test_no_sample_lands_on_a_request_type_that_needs_an_upload(self):
        """The offered samples themselves must stay completable in the portal."""
        for sample in SAMPLES:
            for field in REGISTRY["schemas"][sample["requestTypeId"]]:
                if field["required"]:
                    with self.subTest(f"{sample['requestTypeId']}/{field['id']}"):
                        self.assertIn(CATALOG[field["id"]]["kind"], ASKABLE_KINDS)

    def test_the_catalogue_kind_matches_what_the_registry_validates(self):
        """`phone-tr` is the registry's name for the portal's `phone` input."""
        equivalents = {"phone-tr": "phone", "text": "text", "textarea": "textarea", "date": "date", "tckn": "tckn", "attachment": "attachment"}
        for schema in REGISTRY["schemas"].values():
            for field in schema:
                expected = equivalents.get(field["kind"])
                if expected in ("tckn", "phone", "date", "attachment"):
                    with self.subTest(field["id"]):
                        self.assertEqual(CATALOG[field["id"]]["kind"], expected)

    def test_every_catalogue_entry_is_labelled_in_turkish_for_the_citizen(self):
        for field_id, field in CATALOG.items():
            self.assertTrue(field["label"].strip(), field_id)
            self.assertNotEqual(field["label"], field_id, f"{field_id} etiketi alan kimliğinin kendisi")


class SamplePresentationTests(unittest.TestCase):
    def test_every_sample_is_described_in_turkish_for_the_citizen(self):
        for sample in SAMPLES:
            for key in ("label", "summary", "unitHint", "sampleText"):
                self.assertTrue(sample[key].strip(), f"{sample['requestTypeId']}.{key}")

    def test_samples_are_listed_once_each(self):
        ids = [sample["requestTypeId"] for sample in SAMPLES]
        self.assertEqual(len(set(ids)), len(ids))

    def test_every_sample_addresses_the_authority_the_portal_names(self):
        for sample in SAMPLES:
            with self.subTest(sample["requestTypeId"]):
                self.assertIn(CONTENT["authority"], sample["sampleText"])


if __name__ == "__main__":
    unittest.main()
