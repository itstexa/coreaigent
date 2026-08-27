#!/usr/bin/env python3
"""Lightweight benchmark/quality check for the public document golden dataset."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ALLOWED_TYPES = {"dilekçe", "şikayet", "bilgi_talebi", "başvuru_formu", "itiraz"}


def load_dataset(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_list(value: Any, field_name: str, record_id: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{record_id}: {field_name} must be a list")
    return value


def validate_record(record: dict[str, Any]) -> None:
    record_id = record.get("id")
    if not isinstance(record_id, str):
        raise ValueError("Every record must have a string id")

    document = record.get("document")
    if not isinstance(document, str) or not document.strip():
        raise ValueError(f"{record_id}: document must be a non-empty string")

    expected = record.get("expected")
    if not isinstance(expected, dict):
        raise ValueError(f"{record_id}: expected must be an object")

    document_type = expected.get("document_type")
    if document_type not in ALLOWED_TYPES:
        raise ValueError(f"{record_id}: unsupported document_type '{document_type}'")

    topic = expected.get("topic")
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError(f"{record_id}: topic must be a non-empty string")

    department = expected.get("department") or expected.get("primary_department")
    if not isinstance(department, str) or not department.strip():
        raise ValueError(f"{record_id}: department or primary_department is required")

    related = expected.get("related_departments", [])
    if related:
        ensure_list(related, "related_departments", record_id)
        if not all(isinstance(item, str) and item.strip() for item in related):
            raise ValueError(f"{record_id}: related_departments must only contain non-empty strings")

    critical = ensure_list(expected.get("critical_information"), "critical_information", record_id)
    if not critical or not all(isinstance(item, str) and item.strip() for item in critical):
        raise ValueError(f"{record_id}: critical_information must contain non-empty strings")

    missing = ensure_list(expected.get("missing_fields", []), "missing_fields", record_id)
    if not all(isinstance(item, str) for item in missing):
        raise ValueError(f"{record_id}: missing_fields must contain strings")

    tags = ensure_list(expected.get("tags", []), "tags", record_id)
    if not tags or not all(isinstance(item, str) and item.strip() for item in tags):
        raise ValueError(f"{record_id}: tags must contain non-empty strings")


def summarize_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    records = dataset.get("records")
    if not isinstance(records, list):
        raise ValueError("Dataset root must contain a 'records' list")

    if len(records) != 20:
        raise ValueError(f"Expected 20 records, found {len(records)}")

    ids = [record.get("id") for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate record ids detected")

    for record in records:
        validate_record(record)

    counts = Counter(record["expected"]["document_type"] for record in records)
    expected_distribution = {
        "dilekçe": 4,
        "şikayet": 4,
        "bilgi_talebi": 4,
        "başvuru_formu": 4,
        "itiraz": 4,
    }

    for key, expected_count in expected_distribution.items():
        actual_count = counts.get(key, 0)
        if actual_count != expected_count:
            raise ValueError(f"Distribution mismatch for {key}: expected {expected_count}, got {actual_count}")

    return {
        "total_records": len(records),
        "unique_ids": len(set(ids)),
        "document_types": dict(sorted(counts.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the public-document golden dataset")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "evaluation" / "golden_dataset_v0.1.json",
        help="Path to the JSON dataset file",
    )
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)
    summary = summarize_dataset(dataset)

    print("Dataset benchmark OK")
    print(f"records={summary['total_records']}")
    print(f"unique_ids={summary['unique_ids']}")
    print(f"document_types={summary['document_types']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"dataset benchmark failed: {exc}") from exc
