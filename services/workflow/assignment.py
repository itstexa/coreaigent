"""Small, deterministic F2 assignment policy.

The registry is deliberately local and bounded for the competition runtime.
It is a workload balancer, not an authentication or HR system.
"""

from __future__ import annotations

from datetime import datetime
import re
import unicodedata


DEMO_STAFF = tuple(
    {
        "staff_id": f"{unit}-operator-{number}",
        "display_name": f"{label} Operatörü {number}",
        "role": "operator" if number == 1 else "moderator",
        "unit_id": unit,
    }
    for unit, label in (
        ("beyaz-masa", "Beyaz Masa"),
        ("dijital-hizmetler", "Dijital Hizmetler"),
        ("gelir-tahakkuk", "Gelir ve Tahakkuk"),
        ("ruhsat", "Ruhsat"),
        ("denetim", "Denetim"),
        ("siniflandirilmamis", "Genel Başvuru"),
    )
    for number in (1, 2)
)


AGGRESSION_MARKERS = (
    ("tehdit", 1.0), ("öldür", 1.0), ("şiddet", .9), ("rezalet", .45),
    ("süründür", .7), ("terbiyesiz", .55), ("hırsız", .55), ("yolsuz", .55),
    ("ulan", .35), ("lan", .3), ("bıktım", .35), ("sıkıldım", .35), ("beceriksiz", .6),
    ("dava açarım", .4), ("savcılığa vereceğim", .4),
)

# The intake boundary records the document language before the workflow runs.
# Keep the signal local and deterministic instead of loading a second sentiment
# model in the routing worker.  English markers cover cases where the existing
# translation bridge cannot be loaded; Turkish markers remain the authority's
# primary signal set.
AGGRESSION_MARKERS_EN = (
    ("threat", 1.0), ("kill", 1.0), ("violence", .9), ("unacceptable", .45),
    ("disgrace", .45), ("corrupt", .55), ("lawsuit", .4), ("prosecut", .4),
    ("you will pay", .7),
)


def _marker_matches(haystack, marker):
    """Match words/phrases without treating an embedded English substring as a threat."""
    pattern = rf"(?<!\w){re.escape(marker)}(?!\w)" if " " in marker else rf"(?<!\w){re.escape(marker)}"
    return re.search(pattern, haystack, flags=re.UNICODE) is not None


def _field_value(fields, key):
    entry = (fields or {}).get(key)
    if isinstance(entry, dict):
        return str(entry.get("value") or "").strip()
    return str(entry or "").strip()


def normalize_identity(fields):
    """Return a comparison-only applicant identity; never persist the value."""
    for key in ("applicant-name", "business-name", "supplier-name"):
        value = _field_value(fields, key)
        if value:
            return re.sub(r"\s+", " ", value.casefold()).strip()
    return ""


def behavior_signals(text, *, previous_topic_count=0, same_topic=False, source_language=None):
    """Build bounded, explainable assignment signals without storing petition text."""
    haystack = unicodedata.normalize("NFC", str(text or "").replace("İ", "i")).casefold()
    marker_sets = [AGGRESSION_MARKERS]
    if source_language in {None, "", "unknown", "en"}:
        marker_sets.append(AGGRESSION_MARKERS_EN)
    markers = tuple(marker for marker_set in marker_sets for marker in marker_set)
    matched = [marker for marker, _ in markers if _marker_matches(haystack, marker)]
    score = min(1.0, sum(weight for marker, weight in markers if _marker_matches(haystack, marker)))
    level = "high" if score >= .7 else "elevated" if score > 0 else "normal"
    repeat_count = int(previous_topic_count or 0) + (1 if same_topic else 0)
    return {
        "repeat_count": repeat_count,
        "aggression_score": round(score, 3),
        "aggression_level": level,
        "marker_count": len(matched),
        "priority_mode": repeat_count >= 3 or level in {"elevated", "high"},
    }


def choose_staff(candidates, *, prioritize_resolution=False):
    """Choose by topic resolution rate for flagged cases, otherwise by load."""
    if not candidates:
        return None

    def sort_key(candidate):
        last_assigned = candidate.get("last_assigned_at")
        if isinstance(last_assigned, str):
            try:
                last_assigned = datetime.fromisoformat(last_assigned)
            except ValueError:
                last_assigned = None
        return (
            int(candidate.get("open_count") or 0),
            last_assigned is not None,
            last_assigned or datetime.min,
            str(candidate.get("staff_id") or ""),
        )

    if prioritize_resolution:
        experienced = [candidate for candidate in candidates if int(candidate.get("topic_total") or 0) > 0]
        if experienced:
            def resolution_key(candidate):
                rate = float(candidate.get("resolution_rate") or 0)
                total = int(candidate.get("topic_total") or 0)
                last = candidate.get("last_assigned_at")
                if isinstance(last, str):
                    try:
                        last = datetime.fromisoformat(last)
                    except ValueError:
                        last = None
                return (-rate, -total, int(candidate.get("open_count") or 0), last is not None, last or datetime.min, str(candidate.get("staff_id") or ""))
            return min(experienced, key=resolution_key)
    return min(candidates, key=sort_key)
