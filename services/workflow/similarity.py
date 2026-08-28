"""Small, explainable similarity predicate for BX-03."""

from __future__ import annotations

import re
from datetime import date, datetime


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    raise ValueError("created_at must be a date, datetime, or ISO string")


def _tokens(value):
    return set(re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", (value or "").casefold()))


def similar_case(current, candidate, window_days=30):
    """Explain whether candidate meets same-classification/time threshold."""
    age_days = (_day(current["created_at"]) - _day(candidate["created_at"])).days
    same_classification = current.get("classification") == candidate.get("classification")
    signals = []
    if same_classification:
        signals.append("classification")
    if 0 <= age_days <= window_days:
        signals.append("time")
    if _tokens(current.get("text")) & _tokens(candidate.get("text")):
        signals.append("text")
    if current.get("location") and current.get("location") == candidate.get("location"):
        signals.append("location")
    return {"similar": same_classification and 0 <= age_days <= window_days, "age_days": age_days, "signals": signals}
