"""Deterministic F-05 routing and audience projection rules.

This module deliberately contains no database or model calls: the taxonomy,
current case state and recipient projection are authoritative server inputs.
"""

from __future__ import annotations


FALLBACK_DEPARTMENT_ID = "diger"
FALLBACK_UNIT_ID = "siniflandirilmamis"
MAX_NOTIFICATION_TITLE_CHARACTERS = 200
MAX_NOTIFICATION_BODY_CHARACTERS = 4000
ROUTING_CONFIDENCE_THRESHOLD = 0.80


class RoutingRejected(ValueError):
    """A machine-readable reason why no F-05 route may be created."""


def evaluate_routing(predicted_unit_id, accepted_unit_id=None, confidence=0.0, threshold=ROUTING_CONFIDENCE_THRESHOLD):
    """Pure BX-09 projection: confidence is an estimate, acceptance is truth."""
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    return {
        "predicted_unit_id": predicted_unit_id,
        "confidence": float(confidence),
        "confidence_threshold": float(threshold),
        "needs_review": confidence < threshold,
        "routing_correct": None if accepted_unit_id is None else predicted_unit_id == accepted_unit_id,
        "accepted_unit_id": accepted_unit_id,
    }


def _by_id(items):
    return {item.get("id"): item for item in items if isinstance(item, dict) and item.get("id")}


def _active_chain(taxonomy, department_id, unit_id):
    departments = _by_id(taxonomy.get("departments", []))
    units = _by_id(taxonomy.get("units", []))
    department, unit = departments.get(department_id), units.get(unit_id)
    if not department or not unit or unit.get("departmentId") != department_id:
        raise RoutingRejected("ROUTING_TARGET_INVALID")
    if not department.get("active", True) or not unit.get("active", True):
        raise RoutingRejected("ROUTING_TARGET_INACTIVE")
    return department, unit


def select_route(taxonomy, *, classification_status, completion_status, result_status, department_id, unit_id):
    """Select a single active target without allowing an LLM to choose it."""
    if classification_status != "classified":
        raise RoutingRejected("CLASSIFICATION_NOT_ROUTEABLE")
    if completion_status != "complete":
        raise RoutingRejected("CASE_NOT_COMPLETE")
    if result_status == "draft_ready":
        target_department, target_unit = department_id, unit_id
        route_kind = "classified"
    elif result_status in {"review_required", "not_requested"}:
        target_department, target_unit = FALLBACK_DEPARTMENT_ID, FALLBACK_UNIT_ID
        route_kind = "fallback"
    else:
        raise RoutingRejected("CORRESPONDENCE_NOT_ROUTEABLE")
    _active_chain(taxonomy, target_department, target_unit)
    return {
        "route_kind": route_kind,
        "department_id": target_department,
        "unit_id": target_unit,
        "taxonomy_version": taxonomy.get("taxonomyVersion"),
    }


def notification_payload(audience, case_id, body, operational_context=None):
    """Build persisted-only notification payloads with explicit audience scope."""
    if audience not in {"applicant", "target_unit"}:
        raise ValueError("audience must be applicant or target_unit")
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("case_id is required")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("body is required")
    payload = {
        "audience": audience,
        "case_id": case_id,
        "title": "Başvurunuz işleme alındı" if audience == "applicant" else "Yeni başvuru yönlendirildi",
        "body": body.strip(),
        "email_placeholder": None,
    }
    if audience == "target_unit":
        allowed = {"request_type_id", "validated_fields", "document_summary", "draft_text", "regulation_suggestions"}
        source = operational_context if isinstance(operational_context, dict) else {}
        payload["case_context"] = {key: source[key] for key in allowed if key in source}
    return payload


def normalize_notification_output(payload):
    """Keep only the two approved notification fields from a model object.

    This is a structural recovery for an otherwise valid response which repeats
    supplied case context. It never derives title/body from a differently named
    field, so it cannot publish invented content or a partial response.
    """
    if not isinstance(payload, dict) or not all(isinstance(payload.get(key), str) and payload[key].strip() for key in ("title", "body")):
        raise ValueError("notification title and body are required")
    result = {key: payload[key].strip() for key in ("title", "body")}
    if len(result["title"]) > MAX_NOTIFICATION_TITLE_CHARACTERS or len(result["body"]) > MAX_NOTIFICATION_BODY_CHARACTERS:
        raise ValueError("notification output exceeds bounds")
    return result
