"""Deterministic, review-only abuse signals for BX-04."""

from __future__ import annotations

import re

DEFAULT_CONFIG = {
    "threshold": 0.70,
    "weights": {"duplicate": 0.45, "burst": 0.30, "profanity": 0.25, "threat": 0.50, "harassment": 0.40, "bot_repeat": 0.35},
    "terms": {"profanity": ("küfür", "hakaret"), "threat": ("öldür", "tehdit"), "harassment": ("taciz",)},
}


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def analyze_submission(text, prior_texts=(), recent_count=0, config=None):
    """Return bounded score/signals; criticism and capitals alone never flag."""
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    weights = {**DEFAULT_CONFIG["weights"], **cfg.get("weights", {})}
    terms = {**DEFAULT_CONFIG["terms"], **cfg.get("terms", {})}
    normalized = _normal(text)
    signals = []
    previous = [_normal(item) for item in prior_texts if isinstance(item, str)]
    if normalized and normalized in previous:
        signals.append("duplicate")
    if isinstance(recent_count, int) and recent_count > 5:
        signals.append("burst")
    for name in ("profanity", "threat", "harassment"):
        if any(isinstance(term, str) and term.casefold() in normalized for term in terms.get(name, ())):
            signals.append(name)
    if previous.count(normalized) >= 3 and normalized:
        signals.append("bot_repeat")
    score = min(1.0, max(0.0, sum(float(weights.get(signal, 0.0)) for signal in signals)))
    return {"label": "review" if score >= float(cfg.get("threshold", 0.70)) else "clear", "confidence": score, "risk_score": score, "flagged": score >= float(cfg.get("threshold", 0.70)), "detected_signals": signals}
