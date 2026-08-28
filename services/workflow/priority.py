"""Pure, deterministic BX-08 priority policy.

The policy deliberately accepts a plain mapping so it can be used by the API,
workers, and the contract mock without sharing persistence or model code.
"""
from __future__ import annotations

from datetime import datetime, timezone

LEVELS = ("low", "normal", "high", "urgent")
DEFAULT_POLICY = {
    "version": "priority-policy-v1",
    "urgent_request_types": [],
    "high_request_types": [],
    "urgent_waiting_days": 7,
    "high_waiting_days": 3,
    "urgent_deadline_hours": 24,
    "high_deadline_hours": 72,
}


def _hours_until(value, now):
    if not value:
        return None
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return (when - now).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def calculate_priority(signals=None, policy=None, *, now=None):
    """Return ``level``, policy version, and a human-readable deterministic reason."""
    signals = signals or {}
    cfg = dict(DEFAULT_POLICY)
    cfg.update(policy or {})
    now = now or datetime.now(timezone.utc)
    reasons = []
    level = "normal"
    def raise_to(target, reason):
        nonlocal level
        if LEVELS.index(target) > LEVELS.index(level):
            level = target
        reasons.append(reason)

    request_type = signals.get("request_type") or signals.get("requestTypeId")
    if request_type in cfg["urgent_request_types"]:
        raise_to("urgent", "request type is policy-defined urgent")
    elif request_type in cfg["high_request_types"]:
        raise_to("high", "request type is policy-defined high priority")
    if signals.get("verified_urgency") is True:
        raise_to("urgent", "verified urgency indicator")
    hours = _hours_until(signals.get("deadline"), now)
    if hours is not None and hours <= cfg["urgent_deadline_hours"]:
        raise_to("urgent", "verified deadline is within 24 hours")
    elif hours is not None and hours <= cfg["high_deadline_hours"]:
        raise_to("high", "verified deadline is within 72 hours")
    try:
        waiting = float(signals.get("waiting_days", 0))
    except (TypeError, ValueError):
        waiting = 0
    if waiting >= cfg["urgent_waiting_days"]:
        raise_to("urgent", "case has waited at least 7 days")
    elif waiting >= cfg["high_waiting_days"]:
        raise_to("high", "case has waited at least 3 days")
    if not reasons:
        reasons.append("no qualifying urgency signal; default priority")
    return {"level": level, "policy_version": cfg["version"], "reason": "; ".join(reasons)}


def apply_override(current, level, reason):
    if level not in LEVELS:
        raise ValueError("invalid priority level")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("override reason is required")
    return dict(current, level=level, override_reason=reason.strip())


def queue_order(items):
    """Order rows by priority only; never mutates routing fields or the rows."""
    rank = {level: index for index, level in enumerate(LEVELS)}
    return sorted(items, key=lambda item: -rank.get(item.get("priority", "normal"), 1))
