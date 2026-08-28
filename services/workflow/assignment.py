"""Minimal least-open-case assignment rule for BX-02."""

from __future__ import annotations

import random


def select_assignee(personnel, open_case_counts, unit_id, chooser=None):
    """Choose one member of ``unit_id`` with the fewest open cases.

    ``chooser`` is injectable only for deterministic tests; production uses
    ``random.choice`` for equal minimum loads as required by the policy.
    """
    if not isinstance(unit_id, str) or not unit_id.strip():
        raise ValueError("unit_id is required")
    candidates = [
        person for person in personnel or ()
        if isinstance(person, dict)
        and isinstance(person.get("person_id"), str)
        and person["person_id"].strip()
        and person.get("unit_id") == unit_id
    ]
    if not candidates:
        return None
    counts = open_case_counts if isinstance(open_case_counts, dict) else {}
    def load(person):
        value = counts.get(person["person_id"], 0)
        return value if isinstance(value, int) and value >= 0 else 0
    minimum = min(load(person) for person in candidates)
    tied = [person for person in candidates if load(person) == minimum]
    return (chooser or random.choice)(tied)
