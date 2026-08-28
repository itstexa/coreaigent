"""Small aggregate trend helper for BX-04A."""

from __future__ import annotations

from collections import defaultdict


def flagged_rate(rows, scope, minimum_group=5):
    """Aggregate (scope, day, flagged) rows; suppress groups below minimum."""
    groups = defaultdict(lambda: [0, 0])
    for row in rows or ():
        key = row.get(scope)
        if key is None:
            continue
        bucket = groups[key]
        bucket[0] += 1
        bucket[1] += bool(row.get("flagged"))
    return {key: {"total": total, "flagged": flagged, "rate": flagged / total if total else 0.0}
            for key, (total, flagged) in groups.items() if total >= minimum_group}
